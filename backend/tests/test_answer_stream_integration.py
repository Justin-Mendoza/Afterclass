"""Real upload → ingestion → retrieval → streamed answer, with offline model fixtures."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_ingestion_worker_integration import WordTokenizer
from test_management_integration import management_database  # noqa: F401

from hybrid_rag_search import answer_stream, answers, api, main, management_api, search
from hybrid_rag_search.authorization import Authorization
from hybrid_rag_search.config import Settings
from hybrid_rag_search.database import async_database_url
from hybrid_rag_search.ingestion import runtime
from hybrid_rag_search.management import ManagementService
from hybrid_rag_search.models import SavedAnswer
from hybrid_rag_search.opensearch_index import OpenSearchDocumentIndex, OpenSearchIndexManager
from hybrid_rag_search.providers.fake import FakeEmbeddingProvider, FakeRerankingProvider
from hybrid_rag_search.providers.generation import (
    GenerationCitation,
    GenerationFinishReason,
    GenerationResult,
    GenerationTextDelta,
)
from hybrid_rag_search.seed import (
    DEMO_COLLECTION_ID,
    DEMO_TENANT_ID,
    DEMO_USER_ID,
    ENGINEERING_USER_ID,
    seed_database,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@asynccontextmanager
async def offline_application(database_url: str, root: Path, monkeypatch):
    """Shared by integration tests and a temporary browser runner; never a production mode."""
    index_name = f"hybrid-rag-chunks-v3-stream-{uuid4().hex[:12]}"
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        storage_root=root / "originals",
        ingestion_artifact_root=root / "artifacts",
        cohere_embed_model=FakeEmbeddingProvider.MODEL,
        cohere_embed_dimensions=8,
        opensearch_read_alias=index_name,
        opensearch_write_alias=index_name,
    )
    manager = OpenSearchIndexManager(settings.opensearch_url, index_name, index_name, 8)
    engine = create_async_engine(async_database_url(database_url))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    tasks = set()

    @asynccontextmanager
    async def embeddings(settings):
        yield FakeEmbeddingProvider()

    @asynccontextmanager
    async def reranking(settings):
        yield FakeRerankingProvider()

    class GroundedFixture:
        async def generate(self, request):
            body = request.documents[0].text
            prefix = "STATUS: answered\n"
            return GenerationResult(
                prefix + body,
                GenerationFinishReason.COMPLETE,
                "offline-grounded-fixture",
                "fake",
                citations=(
                    GenerationCitation(
                        len(prefix), len(prefix + body), body, (request.documents[0].id,)
                    ),
                ),
            )

        async def stream(self, request):
            result = await self.generate(request)
            for start in range(0, len(result.text), 8):
                yield GenerationTextDelta(result.text[start : start + 8])
                await asyncio.sleep(0.01)
            yield result

    @asynccontextmanager
    async def generation(settings):
        yield GroundedFixture()

    for module in (api, answer_stream, management_api, main):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(search, "configured_cohere_embeddings", embeddings)
    monkeypatch.setattr(search, "configured_cohere_reranking", reranking)
    monkeypatch.setattr(answers, "configured_cohere_generation", generation)
    monkeypatch.setattr(answers, "load_local_tokenizer", lambda **_: WordTokenizer())
    monkeypatch.setattr(runtime, "configured_cohere_embeddings", embeddings)
    monkeypatch.setattr(runtime, "load_configured_tokenizer", lambda _: WordTokenizer())

    class Publisher:
        async def publish(self, job):
            task = asyncio.create_task(
                runtime.run_configured_job(
                    settings,
                    MagicMock(),
                    OpenSearchDocumentIndex(settings.opensearch_url, index_name, 8),
                    job,
                )
            )
            tasks.add(task)

    policy = Authorization(sessions)
    service = ManagementService(sessions, settings, Publisher())
    app = main.create_app()
    app.dependency_overrides[api.authorization] = lambda: policy
    app.dependency_overrides[management_api.management] = lambda: service
    try:
        await manager.create(index_name)
        await seed_database(database_url)
        yield app, sessions
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()
        async with httpx.AsyncClient(base_url=settings.opensearch_url) as client:
            await client.delete(f"/{index_name}")


@pytest.mark.integration
@pytest.mark.anyio
async def test_upload_processing_streamed_answer_history_and_source_access(
    tmp_path,
    monkeypatch,
    management_database,  # noqa: F811
):
    import json

    async with (
        offline_application(management_database, tmp_path, monkeypatch) as (app, sessions),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        headers = {"X-Demo-User-ID": str(DEMO_USER_ID)}
        base = f"/v1/workspaces/{DEMO_TENANT_ID}"
        text = "Upload receipts last 24 hours. Retrying an upload must reuse the same key."
        upload = await client.post(
            f"{base}/collections/{DEMO_COLLECTION_ID}/documents",
            headers={**headers, "Idempotency-Key": "stream-integration"},
            files={"file": ("receipt-notes.txt", text, "text/plain")},
        )
        assert upload.status_code == 202, upload.text
        receipt = upload.json()
        for _ in range(100):
            job = await client.get(f"{base}/jobs/{receipt['job_id']}", headers=headers)
            assert job.status_code == 200
            if job.json()["status"] in ("failed", "succeeded"):
                break
            await asyncio.sleep(0.05)
        assert job.json()["status"] == "succeeded", job.text
        response = await client.post(
            f"{base}/answers/stream",
            headers=headers,
            json={
                "question": "How long do upload receipts last?",
                "collection_id": str(DEMO_COLLECTION_ID),
            },
        )
        events = [
            json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
        ]
        assert response.status_code == 200 and events[-1]["type"] == "complete", response.text
        final = events[-1]
        assert final["result"]["outcome"] == "answered"
        assert text == final["result"]["text"]
        assert "".join(e["text"] for e in events if e["type"] == "content") == text
        assert final["result"]["evidence"][0]["document_id"] == receipt["document_id"]
        assert final["result"]["citations"][0]["start"] == 0
        history = await client.get(f"{base}/answers/{final['answer_id']}", headers=headers)
        assert history.json()["result"] == final["result"]
        original = await client.get(
            f"{base}/documents/{receipt['document_id']}/content", headers=headers
        )
        assert original.text == text
        other = {"X-Demo-User-ID": str(ENGINEERING_USER_ID)}
        assert (
            await client.get(f"{base}/answers/{final['answer_id']}", headers=other)
        ).status_code == 404
        # A later deletion withholds the entire saved result and the direct source download.
        deleted = await client.delete(f"{base}/documents/{receipt['document_id']}", headers=headers)
        assert deleted.status_code == 204, deleted.text
        hidden = await client.get(f"{base}/answers/{final['answer_id']}", headers=headers)
        assert hidden.json()["available"] is False and hidden.json()["result"] is None
        assert (
            await client.get(f"{base}/documents/{receipt['document_id']}/content", headers=headers)
        ).status_code == 404
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(SavedAnswer)) == 1
