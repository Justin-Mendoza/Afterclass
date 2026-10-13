"""Deterministic management failure/retry and public-contract tests."""

import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from hybrid_rag_search import api, management_api
from hybrid_rag_search.api_errors import APIError
from hybrid_rag_search.authorization import AccessDenied, Authorization, AuthorizedScope
from hybrid_rag_search.config import Settings
from hybrid_rag_search.documents import DocumentNotFound, DocumentUnavailable, UploadResult
from hybrid_rag_search.ingestion.artifacts import ArtifactKind, LocalArtifactStorage, artifact_key
from hybrid_rag_search.ingestion.indexing import IndexWriteError
from hybrid_rag_search.ingestion.jobs import EnqueueResult
from hybrid_rag_search.main import create_app
from hybrid_rag_search.management import ManagementService
from hybrid_rag_search.models import (
    AuditEvent,
    Collection,
    Document,
    IngestionJob,
    IngestionJobStatus,
    Membership,
    UploadReceipt,
)
from hybrid_rag_search.opensearch_index import OpenSearchDocumentIndex
from hybrid_rag_search.seed import DEMO_USER_ID


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def rig(tmp_path):
    session = AsyncMock()
    session.add = MagicMock()
    sessions = MagicMock()
    sessions.return_value.__aenter__.return_value = session
    sessions.begin.return_value.__aenter__.return_value = session
    settings = Settings(
        _env_file=None,
        storage_root=tmp_path / "originals",
        ingestion_artifact_root=tmp_path / "artifacts",
        upload_max_bytes=10,
    )
    publisher = SimpleNamespace(publish=AsyncMock())
    service = ManagementService(sessions, settings, publisher)
    member = Membership(id=uuid4(), tenant_id=uuid4(), user_id=DEMO_USER_ID, role="admin")
    now = datetime.now(UTC)
    collection = Collection(
        id=uuid4(),
        tenant_id=member.tenant_id,
        name="Docs",
        slug="docs",
        description=None,
        created_at=now,
        updated_at=now,
    )
    document = Document(
        id=uuid4(),
        tenant_id=member.tenant_id,
        collection_id=collection.id,
        original_filename="a.txt",
        media_type="text/plain",
        size_bytes=1,
        status="ready",
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )
    job = IngestionJob(
        id=uuid4(),
        tenant_id=member.tenant_id,
        document_id=document.id,
        status="queued",
        stage="parse",
        attempts=0,
        max_attempts=3,
        error_code=None,
        error_message=None,
        created_at=now,
        started_at=None,
        finished_at=None,
        next_attempt_at=None,
    )
    return SimpleNamespace(
        session=session,
        sessions=sessions,
        settings=settings,
        service=service,
        member=member,
        collection=collection,
        document=document,
        job=job,
        publisher=publisher,
    )


@pytest.mark.anyio
async def test_receipt_is_committed_before_dispatch_and_retry_checks_fingerprint(rig):
    r = rig
    r.session.scalar.side_effect = [r.collection, None]
    r.service.originals.upload_in_session = AsyncMock(
        return_value=UploadResult(r.document.id, False)
    )
    r.service.jobs.enqueue_in_session = AsyncMock(
        return_value=EnqueueResult(r.job.id, True, IngestionJobStatus.QUEUED)
    )

    async def committed_dispatch(job):
        assert r.sessions.begin.return_value.__aexit__.called

    r.publisher.publish.side_effect = committed_dispatch
    result = await r.service.upload(r.member, r.collection.id, "one", "a.txt", "text/plain", b"a")
    assert result.document_id == r.document.id and result.dispatch == "sent"
    receipt = next(
        call.args[0]
        for call in r.session.add.call_args_list
        if isinstance(call.args[0], UploadReceipt)
    )
    assert (
        receipt.fingerprint
        == hashlib.sha256(
            json.dumps(
                ["a.txt", "text/plain", hashlib.sha256(b"a").hexdigest()], separators=(",", ":")
            ).encode()
        ).hexdigest()
    )
    r.session.scalar.side_effect = [r.collection, receipt]
    r.session.get.side_effect = [r.document, r.job]
    r.publisher.publish.side_effect = ConnectionError("private error")
    assert (
        await r.service.upload(r.member, r.collection.id, "one", "a.txt", "text/plain", b"a")
    ).dispatch == "pending"
    assert r.service.originals.upload_in_session.await_count == 1
    for body, expected in ((b"b", "idempotency_conflict"), (b"a", "upload_deleted")):
        r.document.status = "deleted"
        r.session.scalar.side_effect = [r.collection, receipt]
        r.session.get.side_effect = [r.document]
        with pytest.raises(APIError) as error:
            await r.service.upload(r.member, r.collection.id, "one", "a.txt", "text/plain", body)
        assert error.value.code == expected
    r.document.status = "ready"
    r.job.status = "failed"
    r.session.scalar.side_effect = [r.collection, receipt]
    r.session.get.side_effect = [r.document, r.job]
    assert (
        await r.service.upload(r.member, r.collection.id, "one", "a.txt", "text/plain", b"a")
    ).dispatch == "not_needed"
    r.session.scalar.side_effect = [None]
    with pytest.raises(APIError, match="Collection not found"):
        await r.service.upload(r.member, r.collection.id, "one", "a.txt", "text/plain", b"a")


@pytest.mark.anyio
async def test_grants_and_metadata_stay_scoped_and_job_failures_are_safe(rig):
    r = rig
    r.session.scalar.return_value = r.collection
    assert await r.service.collection(r.member.tenant_id, r.collection.id) is r.collection
    r.session.scalar.return_value = r.document
    assert await r.service.document(r.member.tenant_id, r.document.id) is r.document
    r.session.scalar.return_value = r.job
    r.job.error_code, r.job.error_message = "parse_failed", "secret/path/content"
    result = await r.service.job(r.member.tenant_id, r.job.id)
    assert (
        result.failure_reason == "Processing failed at parse."
        and "secret" not in result.model_dump_json()
    )
    r.job.error_code = None
    assert (await r.service.job(r.member.tenant_id, r.job.id)).failure_reason is None
    r.session.scalar.return_value = None
    for operation in (r.service.collection, r.service.document, r.service.job):
        with pytest.raises(APIError) as error:
            await operation(r.member.tenant_id, uuid4())
        assert error.value.status == 404
    for permission, grant in (
        ("read", None),
        ("write", SimpleNamespace(permission="read")),
        (None, None),
    ):
        r.session.scalar.side_effect = [r.collection, r.member, grant]
        await r.service.set_grant(r.member, r.collection.id, r.member.id, permission)
        if grant:
            assert grant.permission == "write"
    for rows in ([None, r.member], [r.collection, None]):
        r.session.scalar.side_effect = rows
        with pytest.raises(APIError):
            await r.service.set_grant(r.member, r.collection.id, uuid4(), "read")


@pytest.mark.anyio
async def test_deletion_rejects_running_jobs_and_retries_after_cleanup_failure(rig):
    r = rig
    r.service.originals._document = AsyncMock(return_value=r.document)
    r.session.scalars.return_value = [r.job]
    r.service.index.delete_document = AsyncMock()
    r.service.originals.storage.delete = MagicMock()
    r.job.status = "running"
    with pytest.raises(APIError) as error:
        await r.service.delete_document(r.member, r.document.id)
    assert error.value.code == "document_processing"
    r.service.index.delete_document.assert_not_awaited()
    r.job.status = "queued"
    r.service.index.delete_document.side_effect = IndexWriteError("down", retryable=True)
    with pytest.raises(IndexWriteError):
        await r.service.delete_document(r.member, r.document.id)
    assert r.document.status == "deleting" and r.job.status == "cancelled"
    r.service.index.delete_document.side_effect = None
    r.service.originals.storage.delete.side_effect = OSError("disk down")
    with pytest.raises(OSError):
        await r.service.delete_document(r.member, r.document.id)
    assert r.document.status == "deleting"
    r.service.originals.storage.delete.side_effect = None
    artifacts = LocalArtifactStorage(r.settings.ingestion_artifact_root)
    artifacts.save(artifact_key(r.member.tenant_id, r.job.id, ArtifactKind.PARSED, "a" * 64), b"a")
    await r.service.delete_document(r.member, r.document.id)
    assert r.document.status == "deleted" and r.document.deleted_at is not None
    assert not (artifacts.root / str(r.member.tenant_id) / str(r.job.id)).exists()
    await r.service.delete_document(r.member, r.document.id)
    actions = [
        call.args[0].action
        for call in r.session.add.call_args_list
        if isinstance(call.args[0], AuditEvent)
    ]
    assert actions == ["document.delete_requested", "document.deleted"]
    # A simultaneous successful cleanup is safe when another request finishes first.
    r.document.status = "deleting"
    r.service.originals._document.side_effect = [r.document, SimpleNamespace(status="deleted")]
    await r.service.delete_document(r.member, r.document.id)


def test_job_artifact_deletion_is_scoped_and_rejects_symlinks(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    tenant, job, other = uuid4(), uuid4(), uuid4()
    storage.delete_job(tenant, job)
    with pytest.raises(ValueError):
        storage.delete_job("bad", job)
    storage.save(artifact_key(tenant, other, ArtifactKind.PARSED, "b" * 64), b"keep")
    jobdir = tmp_path / str(tenant) / str(job)
    jobdir.symlink_to(tmp_path / str(tenant) / str(other), target_is_directory=True)
    with pytest.raises(ValueError):
        storage.delete_job(tenant, job)
    assert list((tmp_path / str(tenant) / str(other)).rglob("*.json"))


@pytest.mark.anyio
async def test_management_permission_levels_and_hidden_resources(rig):
    r = rig
    auth = Authorization(r.sessions)
    auth.user = AsyncMock(return_value=SimpleNamespace(id=DEMO_USER_ID))
    r.session.scalar.return_value = r.member
    assert await auth.membership(DEMO_USER_ID, r.member.tenant_id) is r.member
    for member in (None, SimpleNamespace(role="unknown")):
        r.session.scalar.return_value = member
        with pytest.raises(AccessDenied):
            await auth.membership(DEMO_USER_ID, r.member.tenant_id)
    auth.membership = AsyncMock(return_value=r.member)
    auth.scope = AsyncMock()
    assert await auth.require(DEMO_USER_ID, r.member.tenant_id, "manage") is r.member
    r.member.role = "member"
    with pytest.raises(AccessDenied):
        await auth.require(DEMO_USER_ID, r.member.tenant_id, "manage")
    for grant, required, allowed in (
        ("read", "read", True),
        ("read", "write", False),
        ("write", "write", True),
        ("write", "manage", False),
        ("manage", "manage", True),
        (None, "read", False),
    ):
        r.session.scalar.return_value = grant
        if allowed:
            assert (
                await auth.require(DEMO_USER_ID, r.member.tenant_id, required, r.collection.id)
                is r.member
            )
        else:
            with pytest.raises(AccessDenied):
                await auth.require(DEMO_USER_ID, r.member.tenant_id, required, r.collection.id)


def test_management_api_contracts_and_error_boundaries(rig, monkeypatch):
    r = rig
    policy = SimpleNamespace(
        sessions=r.sessions,
        user=AsyncMock(),
        require=AsyncMock(return_value=r.member),
        scope=AsyncMock(
            return_value=AuthorizedScope(DEMO_USER_ID, r.member.tenant_id, (r.collection.id,))
        ),
    )
    app = create_app()
    app.dependency_overrides[api.authorization] = lambda: policy
    app.dependency_overrides[management_api.management] = lambda: r.service
    base = f"/v1/workspaces/{r.member.tenant_id}"
    path = base + f"/collections/{r.collection.id}"
    docpath = base + f"/documents/{r.document.id}"
    headers = {"X-Demo-User-ID": str(DEMO_USER_ID), "Idempotency-Key": "one"}
    with TestClient(app) as client:
        r.session.scalars.return_value = [r.collection]
        assert client.get(base + "/collections", headers=headers).json()[0]["slug"] == "docs"
        r.session.scalar.return_value = r.collection
        assert client.get(path, headers=headers).status_code == 200
        r.session.flush.side_effect = IntegrityError("sql", {}, Exception("duplicate"))
        assert (
            client.post(
                base + "/collections", headers=headers, json={"name": "X", "slug": "x"}
            ).json()["error"]["code"]
            == "collection_conflict"
        )
        r.session.flush.side_effect = None

        def add(row):
            if isinstance(row, Collection):
                row.id, row.created_at, row.updated_at = (
                    uuid4(),
                    r.collection.created_at,
                    r.collection.updated_at,
                )

        r.session.add.side_effect = add
        assert (
            client.post(
                base + "/collections", headers=headers, json={"name": "X", "slug": "x"}
            ).status_code
            == 201
        )
        assert client.patch(path, headers=headers, json={"name": "Updated"}).status_code == 200
        r.session.scalar.return_value = None
        assert client.patch(path, headers=headers, json={"name": "X"}).status_code == 404
        r.session.execute.return_value = [(r.member, "Admin")]
        assert client.get(base + "/members", headers=headers).status_code == 200
        r.session.scalars.return_value = [
            SimpleNamespace(membership_id=r.member.id, permission="read")
        ]
        assert client.get(path + "/grants", headers=headers).status_code == 200
        r.service.set_grant = AsyncMock()
        grantpath = path + f"/grants/{r.member.id}"
        assert (
            client.put(grantpath, headers=headers, json={"permission": "read"}).status_code == 204
        )
        assert client.delete(grantpath, headers=headers).status_code == 204
        r.session.scalars.return_value = [r.document]
        assert client.get(path + "/documents", headers=headers).status_code == 200
        r.service.upload = AsyncMock(
            return_value={
                "document_id": r.document.id,
                "job_id": r.job.id,
                "duplicate": False,
                "dispatch": "pending",
            }
        )
        for name, content, mime, status in (
            ("a.txt", b"a", "text/plain", 202),
            ("a.txt", b"x" * 11, "text/plain", 413),
            ("a" * 256, b"a", "text/plain", 422),
            ("a.zip", b"a", "application/zip", 415),
        ):
            assert (
                client.post(
                    path + "/documents", headers=headers, files={"file": (name, content, mime)}
                ).status_code
                == status
            )
        r.service.upload.side_effect = OSError("private details")
        response = client.post(
            path + "/documents", headers=headers, files={"file": ("a.txt", b"a", "text/plain")}
        )
        assert response.status_code == 503 and "private" not in response.text
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
        r.service.upload.side_effect = DocumentUnavailable()
        response = client.post(
            path + "/documents", headers=headers, files={"file": ("a.txt", b"a", "text/plain")}
        )
        assert (
            response.status_code == 409
            and response.json()["error"]["code"] == "document_unavailable"
        )
        r.service.document = AsyncMock(return_value=r.document)
        assert client.get(docpath, headers=headers).status_code == 200
        r.session.scalar.return_value = r.job
        assert client.get(base + f"/jobs/{r.job.id}", headers=headers).status_code == 200
        r.service.document.side_effect = APIError(404, "not_found", "Document not found.")
        assert client.get(docpath, headers=headers).status_code == 404
        r.service.document.side_effect = None
        for status in (401, 403):
            policy.scope.side_effect = AccessDenied(status, "denied")
            assert client.get(docpath, headers=headers).status_code == (
                401 if status == 401 else 404
            )
        policy.scope.side_effect = None
        r.service.delete_document = AsyncMock()
        assert client.delete(docpath, headers=headers).status_code == 204
        for error, status in ((DocumentNotFound(), 404), (OSError(), 503), (ValueError(), 503)):
            r.service.delete_document.side_effect = error
            assert client.delete(docpath, headers=headers).status_code == status
        r.service.document.side_effect = SQLAlchemyError("secret connection info")
        response = client.get(docpath, headers=headers)
        assert response.status_code == 503 and "secret" not in response.text
        assert client.get(base + "/collections?limit=0", headers=headers).status_code == 422
        schema = client.get("/openapi.json").json()
        assert schema["paths"][
            path.replace(str(r.member.tenant_id), "{workspace_id}").replace(
                str(r.collection.id), "{collection_id}"
            )
            + "/documents"
        ]["post"]["requestBody"]["content"].get("multipart/form-data")
    composed = management_api.management(policy)
    assert composed.sessions is r.sessions


@pytest.mark.anyio
async def test_index_delete_checks_partial_failures():
    for result in ({"failures": ["failed"]}, {"timed_out": True}, {"version_conflicts": 1}):
        index = OpenSearchDocumentIndex(
            "http://test",
            "index",
            3,
            transport=httpx.MockTransport(
                lambda request, result=result: httpx.Response(200, json=result)
            ),
        )
        with pytest.raises(IndexWriteError) as error:
            await index.delete_document(str(uuid4()), str(uuid4()))
        assert error.value.code == "document_delete_incomplete"


def test_excluded_document_filter_validation_and_storage_error_response(rig, monkeypatch):
    from hybrid_rag_search.retrieval_filters import RetrievalFilters

    for ids in ([uuid4()], ("bad",)):
        with pytest.raises(ValueError, match="Excluded document"):
            RetrievalFilters(uuid4(), excluded_document_ids=ids)
    r = rig
    policy = SimpleNamespace(document_scope=AsyncMock(), sessions=r.sessions)
    app = create_app()
    app.dependency_overrides[api.authorization] = lambda: policy
    monkeypatch.setattr(
        api,
        "DocumentService",
        lambda *args: SimpleNamespace(fetch=AsyncMock(side_effect=OSError("private path"))),
    )
    with TestClient(app) as client:
        response = client.get(
            f"/v1/workspaces/{r.member.tenant_id}/documents/{r.document.id}/content"
        )
        assert (
            response.status_code == 503
            and response.json()["error"]["code"] == "storage_unavailable"
        )
