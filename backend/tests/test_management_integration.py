"""Day 17 API and race checks against PostgreSQL and isolated OpenSearch data."""

import asyncio
import hashlib
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_hybrid_retrieval_integration import indexed_document

from hybrid_rag_search import api, management_api
from hybrid_rag_search.authorization import Authorization
from hybrid_rag_search.config import get_settings
from hybrid_rag_search.database import async_database_url
from hybrid_rag_search.ingestion.artifacts import ArtifactKind, LocalArtifactStorage, artifact_key
from hybrid_rag_search.ingestion.claims import JobClaimer
from hybrid_rag_search.ingestion.indexing import IndexWriteError
from hybrid_rag_search.main import create_app
from hybrid_rag_search.management import ManagementService
from hybrid_rag_search.models import (
    AuditEvent,
    Document,
    IngestionJob,
    Membership,
    Tenant,
    UploadReceipt,
    User,
)
from hybrid_rag_search.opensearch_index import OpenSearchIndexManager
from hybrid_rag_search.seed import DEMO_USER_ID, ENGINEERING_USER_ID, HR_USER_ID, SECOND_USER_ID


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def management_database():
    """Audit records are append-only, so own and drop the entire test database."""
    database = f"day17_test_{uuid4().hex}"
    admin_engine = create_async_engine(
        async_database_url(get_settings().database_url), isolation_level="AUTOCOMMIT"
    )
    async with admin_engine.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{database}"'))
    url = async_database_url(get_settings().database_url).set(database=database)
    database_url = url.render_as_string(hide_password=False)
    try:
        for arguments in (("upgrade", "head"), ("downgrade", "-1"), ("upgrade", "head")):
            migrated = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, "-m", "alembic", "--config", "backend/alembic.ini", *arguments],
                env={**os.environ, "DATABASE_URL": database_url},
                capture_output=True,
                text=True,
            )
            assert migrated.returncode == 0, migrated.stderr
        yield database_url
    finally:
        async with admin_engine.connect() as connection:
            await connection.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))
        await admin_engine.dispose()


@pytest.mark.integration
@pytest.mark.anyio
async def test_management_api_lifecycle_permissions_retries_and_cleanup(
    tmp_path: Path, monkeypatch, management_database
):
    database_url = management_database
    tenant, foreign = uuid4(), uuid4()
    index_name = f"hybrid-rag-chunks-v3-mgmt-{uuid4().hex[:12]}"
    settings = get_settings().model_copy(
        update={
            "database_url": database_url,
            "storage_root": tmp_path / "originals",
            "ingestion_artifact_root": tmp_path / "artifacts",
            "opensearch_write_alias": index_name,
            "opensearch_read_alias": index_name,
            "upload_max_bytes": 100,
            "cohere_embed_dimensions": 3,
        }
    )
    engine = create_async_engine(async_database_url(settings.database_url))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    manager = OpenSearchIndexManager(settings.opensearch_url, "unused-read", "unused-write", 3)

    class Publisher:
        broken = False
        calls = []

        async def publish(self, job):
            self.calls.append(job)
            if self.broken:
                raise ConnectionError("Redis down")

    publisher = Publisher()
    service = ManagementService(sessions, settings, publisher)
    policy = Authorization(sessions)
    app = create_app()
    app.dependency_overrides[api.authorization] = lambda: policy
    app.dependency_overrides[management_api.management] = lambda: service
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    members = {
        user: uuid4() for user in (DEMO_USER_ID, ENGINEERING_USER_ID, HR_USER_ID, SECOND_USER_ID)
    }
    users_created = []
    try:
        await manager.create(index_name)
        async with sessions.begin() as session:
            for user, name in (
                (DEMO_USER_ID, "Admin"),
                (ENGINEERING_USER_ID, "Engineer"),
                (HR_USER_ID, "HR"),
                (SECOND_USER_ID, "Other"),
            ):
                created = await session.scalar(
                    insert(User)
                    .values(id=user, email=f"{user}@management.test", display_name=name)
                    .on_conflict_do_nothing()
                    .returning(User.id)
                )
                if created:
                    users_created.append(created)
            session.add_all(
                [Tenant(id=t, name="Management", slug=f"management-{t}") for t in (tenant, foreign)]
            )
            await session.flush()
            session.add_all(
                [
                    Membership(
                        id=m,
                        user_id=u,
                        tenant_id=foreign if u == SECOND_USER_ID else tenant,
                        role="admin" if u in (DEMO_USER_ID, SECOND_USER_ID) else "member",
                    )
                    for u, m in members.items()
                ]
            )
        base = f"/v1/workspaces/{tenant}"
        headers = {"X-Demo-User-ID": str(DEMO_USER_ID)}
        engineer = {"X-Demo-User-ID": str(ENGINEERING_USER_ID)}
        hr = {"X-Demo-User-ID": str(HR_USER_ID)}
        other = {"X-Demo-User-ID": str(SECOND_USER_ID)}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def upload(key="one", content=b"hello", user=headers, filename="hello.txt"):
                return await client.post(
                    upload_path,
                    headers={**user, "Idempotency-Key": key},
                    files={"file": (filename, content, "text/plain")},
                )

            assert (await client.get(base + "/collections")).status_code == 401
            assert (
                await client.post(
                    base + "/collections", headers=engineer, json={"name": "Docs", "slug": "docs"}
                )
            ).status_code == 403
            created = await client.post(
                base + "/collections", headers=headers, json={"name": "Docs", "slug": "docs"}
            )
            assert created.status_code == 201, created.text
            collection = created.json()["id"]
            path = base + f"/collections/{collection}"
            upload_path = path + "/documents"
            assert (
                await client.post(
                    base + "/collections",
                    headers=headers,
                    json={"name": "Duplicate", "slug": "docs"},
                )
            ).status_code == 409
            assert (await client.get(path, headers=other)).status_code == 403
            assert (await client.get(path, headers=engineer)).status_code == 404
            assert (
                await client.get(base + "/collections?limit=1&offset=1", headers=headers)
            ).json() == []
            assert (await client.get(base + "/members", headers=headers)).status_code == 200
            grant_path = path + f"/grants/{members[ENGINEERING_USER_ID]}"
            foreign_grant = path + f"/grants/{members[SECOND_USER_ID]}"
            assert (
                await client.put(foreign_grant, headers=headers, json={"permission": "read"})
            ).status_code == 404
            for permission in ("read", "write", "manage"):
                assert (
                    await client.put(grant_path, headers=headers, json={"permission": permission})
                ).status_code == 204
                assert (await client.get(path, headers=engineer)).status_code == 200
                edited = await client.patch(path, headers=engineer, json={"name": "Edited"})
                assert edited.status_code == (200 if permission == "manage" else 403)
                assert (
                    await client.get(
                        base + f"/members?collection_id={collection}", headers=engineer
                    )
                ).status_code == (200 if permission == "manage" else 403)
                response = await upload(key=f"grant-{permission}", user=engineer)
                assert response.status_code == (403 if permission == "read" else 202)
            assert (await client.get(path + "/grants", headers=engineer)).status_code == 200
            assert (
                await client.put(
                    path + f"/grants/{members[HR_USER_ID]}",
                    headers=engineer,
                    json={"permission": "read"},
                )
            ).status_code == 204
            assert (await upload(user=hr)).status_code == 403
            assert (await upload(content=b"x" * 101)).status_code == 413
            assert (
                await client.post(
                    upload_path, headers=headers, files={"file": ("x.txt", b"x", "text/plain")}
                )
            ).status_code == 422
            assert (
                await client.post(
                    upload_path,
                    headers={**headers, "Idempotency-Key": "zip"},
                    files={"file": ("x.zip", b"x", "application/zip")},
                )
            ).status_code == 415
            saved = service.originals.storage.save

            def disk_failure(*args):
                raise OSError("disk full")

            monkeypatch.setattr(service.originals.storage, "save", disk_failure)
            assert (await upload("disk-failure", b"new content")).status_code == 503
            async with sessions() as session:
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(UploadReceipt)
                        .where(UploadReceipt.key == "disk-failure")
                    )
                    == 0
                )
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(Document)
                        .where(Document.content_hash == hashlib.sha256(b"new content").hexdigest())
                    )
                    == 0
                )
            monkeypatch.setattr(service.originals.storage, "save", saved)
            responses = await asyncio.gather(*[upload() for _ in range(3)])
            assert all(r.status_code == 202 for r in responses)
            results = [r.json() for r in responses]
            assert len({r["document_id"] for r in results}) == 1
            assert len({r["job_id"] for r in results}) == 1
            assert (await upload(content=b"different")).status_code == 409
            assert (await upload(filename="renamed.txt")).status_code == 409
            original = results[0]
            document, job_id = UUID(original["document_id"]), UUID(original["job_id"])
            doc_path = base + f"/documents/{document}"
            job_path = base + f"/jobs/{job_id}"
            assert (await client.get(upload_path, headers=hr)).json()[0]["id"] == str(document)
            assert (await client.get(doc_path + "/content", headers=hr)).content == b"hello"
            assert (await client.get(doc_path, headers=other)).status_code == 404
            assert (await client.get(job_path, headers=other)).status_code == 404
            assert (await client.get(doc_path, headers=headers)).json()["status"] == "processing"
            assert (await client.get(job_path, headers=hr)).json()["status"] == "queued"
            assert (await client.delete(doc_path, headers=hr)).status_code == 403
            publisher.broken = True
            pending = await upload()
            assert pending.json()["dispatch"] == "pending"
            publisher.broken = False
            assert (await upload()).json()["dispatch"] == "sent"
            claimer = JobClaimer(sessions)
            claimed = await claimer.claim(job_id)
            assert claimed is not None
            assert (await client.delete(doc_path, headers=headers)).json()["error"][
                "code"
            ] == "document_processing"
            async with sessions.begin() as session:
                await session.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id == job_id)
                    .values(
                        status="failed",
                        lease_token=None,
                        lease_expires_at=None,
                        error_code="parse_failed",
                        error_message="secret provider detail",
                    )
                )
            failed = (await client.get(job_path, headers=headers)).json()
            assert failed["error_code"] == "parse_failed" and "secret" not in str(failed)
            assert (await upload()).json()["dispatch"] == "not_needed"
            await service.index.replace_document(
                replace(
                    indexed_document(tenant, UUID(collection), author="admin", suffix="a"),
                    document_id=document,
                )
            )
            artifacts = LocalArtifactStorage(settings.ingestion_artifact_root)
            artifacts.save(artifact_key(tenant, job_id, ArtifactKind.PARSED, "a" * 64), b"artifact")
            original_delete = service.index.delete_document

            async def fail(*args):
                raise IndexWriteError("opensearch_unavailable", retryable=True)

            monkeypatch.setattr(service.index, "delete_document", fail)
            assert (await client.delete(doc_path, headers=headers)).status_code == 503
            assert (await client.get(doc_path, headers=headers)).json()["status"] == "deleting"
            assert (await client.get(doc_path + "/content", headers=headers)).status_code == 404
            assert document in (await policy.scope(DEMO_USER_ID, tenant)).excluded_document_ids
            search = await client.post(
                "/v1/search",
                headers=headers,
                json={
                    "workspace_id": str(tenant),
                    "query": "password",
                    "mode": "bm25",
                    "debug": True,
                },
            )
            assert search.status_code == 200 and search.json()["chunks"] == []
            assert (await upload()).status_code == 409
            monkeypatch.setattr(service.index, "delete_document", original_delete)
            assert (await client.delete(doc_path, headers=headers)).status_code == 204
            assert (await client.delete(doc_path, headers=headers)).status_code == 204
            assert not list(settings.storage_root.rglob("*.bin"))
            assert not (settings.ingestion_artifact_root / str(tenant) / str(job_id)).exists()
            chunks = await manager._request(
                "POST", f"/{index_name}/_count", json={"query": {"match_all": {}}}
            )
            assert chunks.json()["count"] == 0
            assert (await client.get(doc_path, headers=headers)).json()["status"] == "deleted"
            assert (await client.get(job_path, headers=headers)).status_code == 200
            assert (await client.get(upload_path, headers=headers)).json() == []
            replacement = await upload("replacement")
            assert replacement.json()["document_id"] != str(document)
            # A delete/claim race has exactly two safe outcomes.
            replacement_doc = UUID(replacement.json()["document_id"])
            replacement_job = UUID(replacement.json()["job_id"])
            delete_result, claim_result = await asyncio.gather(
                client.delete(base + f"/documents/{replacement_doc}", headers=headers),
                claimer.claim(replacement_job),
            )
            assert (delete_result.status_code == 204 and claim_result is None) or (
                delete_result.status_code == 409 and claim_result is not None
            )
            if claim_result is not None:
                async with sessions.begin() as session:
                    await session.execute(
                        update(IngestionJob)
                        .where(IngestionJob.id == replacement_job)
                        .values(
                            status="failed",
                            lease_token=None,
                            lease_expires_at=None,
                        )
                    )
                assert (
                    await client.delete(base + f"/documents/{replacement_doc}", headers=headers)
                ).status_code == 204
            assert (await client.delete(grant_path, headers=headers)).status_code == 204
            assert (await client.get(path, headers=engineer)).status_code == 404
            async with sessions() as session:
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(UploadReceipt)
                        .where(UploadReceipt.tenant_id == tenant)
                    )
                    == 4
                )
                actions = list(
                    await session.scalars(
                        select(AuditEvent.action).where(AuditEvent.tenant_id == tenant)
                    )
                )
                assert actions.count("document.deleted") == 2
                assert actions.count("document.delete_requested") == 2
    finally:
        try:
            await manager._request("DELETE", f"/{index_name}")
        finally:
            await engine.dispose()
