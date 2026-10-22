"""Offline streaming contracts, resource lifetime, and history failure boundaries."""

import asyncio
import json
from contextlib import aclosing, asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import cohere
import httpx
import pytest
from cohere.core import ApiError
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from test_answer_history import policy_fixture
from test_answers import WordTokenizer, evidence, generated

from hybrid_rag_search import answer_stream as transport
from hybrid_rag_search import api
from hybrid_rag_search.answers import AnswerDraft, AnswerProgress, AnswerResult, AnswerService
from hybrid_rag_search.authorization import AccessDenied
from hybrid_rag_search.config import Settings
from hybrid_rag_search.main import create_app
from hybrid_rag_search.providers.cohere_generation import CohereGenerationProvider
from hybrid_rag_search.providers.errors import ProviderError
from hybrid_rag_search.providers.generation import (
    GenerationDocument,
    GenerationMessage,
    GenerationRequest,
    GenerationTextDelta,
    MessageRole,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


REQUEST = GenerationRequest(
    (GenerationMessage(MessageRole.USER, "What is supported?"),),
    100,
    (GenerationDocument("chunk-a", "Retries reuse the same key."),),
)


def wire(events):
    return "".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events)


def delta(text):
    return {"type": "content-delta", "index": 0, "delta": {"message": {"content": {"text": text}}}}


def finish(reason="COMPLETE"):
    return {
        "type": "message-end",
        "delta": {
            "finish_reason": reason,
            "usage": {
                "tokens": {"input_tokens": 50, "output_tokens": 12},
                "billed_units": {"input_tokens": 50, "output_tokens": 12},
            },
        },
    }


@pytest.mark.anyio
async def test_real_sdk_stream_assembly_citations_usage_and_no_retry():
    output = generated()
    calls = []

    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body["stream"] is True and body["documents"][0]["id"] == "chunk-a"
        citation = output.citations[0]
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=wire(
                [
                    {
                        "type": "message-start",
                        "id": "fixture",
                        "delta": {"message": {"role": "assistant"}},
                    },
                    delta(output.text[:9]),
                    delta(output.text[9:]),
                    {
                        "type": "citation-start",
                        "index": 0,
                        "delta": {
                            "message": {
                                "citations": {
                                    "start": citation.start,
                                    "end": citation.end,
                                    "text": citation.text,
                                    "sources": [
                                        {
                                            "type": "document",
                                            "id": "chunk-a",
                                            "document": {"text": "ignored"},
                                        }
                                    ],
                                }
                            }
                        },
                    },
                    {"type": "citation-end", "index": 0},
                    finish(),
                ]
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        provider = CohereGenerationProvider(
            cohere.AsyncClientV2(api_key="test", httpx_client=http), model="fixture"
        )
        values = [item async for item in provider.stream(REQUEST)]
    assert len(calls) == 1
    assert "".join(item.text for item in values[:-1]) == output.text
    final = values[-1]
    assert final.text == output.text and final.citations == output.citations
    assert final.usage.billed_output_tokens == 12 and final.usage.estimated_cost_usd is not None
    assert "ignored" not in repr(final)


class FakeSDK:
    def __init__(self, events=(), error=None, wait=False):
        self.events, self.error, self.wait, self.closed = events, error, wait, False

    async def chat_stream(self, **kwargs):
        try:
            if self.error:
                raise self.error
            for value in self.events:
                yield SimpleNamespace(model_dump=lambda value=value, **_: value)
            if self.wait:
                await asyncio.sleep(100)
        finally:
            self.closed = True


@pytest.mark.anyio
@pytest.mark.parametrize(
    "events",
    [
        [],
        [delta("hi")],
        [delta("hi"), finish(), delta("extra")],
        [{"type": "tool-call-start"}],
        [delta(123)],
        [delta("x" * 100_001)],
        [{"type": "citation-start", "delta": {"message": {"citations": {}}}}],
        [delta("hi"), finish("TOOL_CALL")],
        [delta("hi"), {"type": "message-end", "delta": {}}],
        [delta(" "), finish()],
        [
            {
                "type": "citation-start",
                "delta": {
                    "message": {
                        "citations": {
                            "start": 0,
                            "end": 1,
                            "text": "x",
                            "sources": [{"type": "document", "id": "a"}],
                        }
                    }
                },
            }
        ]
        * 257,
    ],
)
async def test_stream_provider_rejects_malformed_incomplete_or_excessive_output(events):
    sdk = FakeSDK(events)
    provider = CohereGenerationProvider(sdk, model="fixture")
    with pytest.raises(ProviderError, match="invalid_response"):
        _ = [item async for item in provider.stream(REQUEST)]
    assert sdk.closed


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error,code",
    [
        (httpx.ConnectError("private"), "unavailable"),
        (httpx.ReadTimeout("private"), "timeout"),
        (ApiError(status_code=401, body="private"), "authentication"),
        (ApiError(status_code=429, body="private"), "rate_limited"),
        (ApiError(status_code=503, body="private"), "unavailable"),
        (ApiError(status_code=400, body="private"), "invalid_request"),
        (ValueError("private"), "invalid_response"),
    ],
)
async def test_stream_provider_errors_are_safe(error, code):
    sdk = FakeSDK(error=error)
    with pytest.raises(ProviderError) as caught:
        _ = [item async for item in CohereGenerationProvider(sdk, model="fixture").stream(REQUEST)]
    assert caught.value.code == code and "private" not in str(caught.value) and sdk.closed


@pytest.mark.anyio
async def test_provider_timeout_and_close_before_completion():
    sdk = FakeSDK(wait=True)
    with pytest.raises(ProviderError, match="timeout"):
        _ = [
            item
            async for item in CohereGenerationProvider(
                sdk, model="fixture", timeout_seconds=0.01
            ).stream(REQUEST)
        ]
    assert sdk.closed
    sdk = FakeSDK([delta("draft")], wait=True)
    async with aclosing(CohereGenerationProvider(sdk, model="fixture").stream(REQUEST)) as updates:
        assert (await anext(updates)).text == "draft"
    assert sdk.closed


def service_fixture(parts=None, result=None, error=None):
    policy, scope = policy_fixture()
    item = evidence(scope)
    final = result or generated()
    state = SimpleNamespace(closed=False)

    async def stream(request):
        try:
            for part in (
                parts if parts is not None else [final.text[:4], final.text[4:20], final.text[20:]]
            ):
                if isinstance(part, str):
                    yield GenerationTextDelta(part)
                else:
                    yield part
            if error:
                raise error
            if result is not False:
                yield final
        finally:
            state.closed = True

    provider = SimpleNamespace(stream=stream)
    retrieval = SimpleNamespace(
        search=AsyncMock(return_value={"chunks": [item.model_dump(mode="json")]})
    )
    service = AnswerService(Settings(_env_file=None), retrieval, provider, WordTokenizer())
    return policy, scope, service, state


@pytest.mark.anyio
async def test_answer_draft_hides_header_and_shares_validation():
    _, scope, service, state = service_fixture()
    updates = [item async for item in service.stream(scope, "Question")]
    assert (
        "".join(item.text for item in updates if isinstance(item, AnswerDraft))
        == generated().text.split("\n", 1)[1]
    )
    assert updates[-1].outcome == "answered" and updates[-1].citations[0].start == 0
    assert [item.stage for item in updates if isinstance(item, AnswerProgress)] == [
        "retrieving",
        "generating",
        "validating",
    ]
    assert state.closed


@pytest.mark.anyio
async def test_stream_empty_evidence_and_failure_abstention_and_bad_header():
    _, scope, service, _ = service_fixture()
    service.retrieval.search.return_value = {"chunks": []}
    assert [item async for item in service.stream(scope, "Question")][
        -1
    ].outcome == "insufficient_evidence"
    _, scope, service, state = service_fixture(result=generated(status="insufficient_evidence"))
    updates = [item async for item in service.stream(scope, "Question")]
    assert not any(isinstance(item, AnswerDraft) for item in updates)
    assert updates[-1].text == "The supplied evidence is insufficient to answer this question."
    for parts, result, error, code in [
        (["garbage\nrejected"], None, None, "invalid_answer_status"),
        (["x" * 101], None, None, "invalid_answer_status"),
        (["STATUS: answered\nDraft"], False, None, "invalid_response"),
        ([generated(), GenerationTextDelta("bad")], None, None, "invalid_response"),
        ([generated()], None, None, "invalid_response"),
        ([], None, ProviderError("unavailable"), "unavailable"),
    ]:
        _, scope, service, state = service_fixture(parts, result, error)
        updates = [item async for item in service.stream(scope, "Question")]
        assert updates[-1].outcome == "failed" and updates[-1].error_code == code
        assert state.closed


def setup_stream(monkeypatch, updates=None, error=None, wait=False, timeout=90):
    policy, scope = policy_fixture()
    state = SimpleNamespace(closed=False)

    async def stream(*args):
        try:
            for update in updates or []:
                yield update
            if error:
                raise error
            if wait:
                await asyncio.sleep(100)
        finally:
            state.closed = True

    @asynccontextmanager
    async def configured(settings):
        yield SimpleNamespace(stream=stream)

    monkeypatch.setattr(transport, "configured_answer_service", configured)
    return policy, scope, state, Settings(_env_file=None, answer_request_timeout_seconds=timeout)


def parsed(frames):
    return [
        json.loads(line[6:])
        for frame in frames
        for line in frame.splitlines()
        if line.startswith("data: ")
    ]


@pytest.mark.anyio
async def test_ordered_events_save_and_one_terminal_with_real_history(monkeypatch):
    final = AnswerResult(outcome="partial", text="Supported portion")
    policy, scope, state, settings = setup_stream(
        monkeypatch, [AnswerProgress("generating"), AnswerDraft("draft\nevent: error"), final]
    )
    frames = [frame async for frame in transport.answer_events(policy, scope, "Question", settings)]
    events = parsed(frames)
    assert [e["type"] for e in events] == [
        "progress",
        "content",
        "progress",
        "citations",
        "complete",
    ]
    assert [frame.splitlines()[0] for frame in frames] == [f"id: {i}" for i in range(1, 6)]
    result = events[-1]["result"]
    assert (
        result["text"] == "Supported portion"
        and result["configuration"]["timings"]["first_content_ms"] >= 0
    )
    assert policy.sessions.session.row.result == result and state.closed
    assert "draft" not in repr(policy.sessions.session.row.result)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure,code",
    [
        (
            AnswerResult(outcome="failed", text="", error_code="invalid_citation"),
            "invalid_citation",
        ),
        (ValueError("private"), "answer_unavailable"),
        (OSError("private"), "answer_unavailable"),
        (RuntimeError("private"), "answer_failed"),
    ],
)
async def test_stream_failure_has_safe_saved_terminal_record(monkeypatch, failure, code):
    updates = (
        [AnswerDraft("discard me"), failure]
        if isinstance(failure, AnswerResult)
        else [AnswerDraft("discard me")]
    )
    policy, scope, state, settings = setup_stream(
        monkeypatch, updates, None if isinstance(failure, AnswerResult) else failure
    )
    events = parsed(
        [frame async for frame in transport.answer_events(policy, scope, "Question", settings)]
    )
    assert events[-1]["type"] == "error" and events[-1]["code"] == code
    assert events[-1]["answer_id"] and policy.sessions.session.row.result["outcome"] == "failed"
    assert "private" not in json.dumps(events) and state.closed


@pytest.mark.anyio
async def test_missing_terminal_timeout_and_storage_failure(monkeypatch):
    policy, scope, state, settings = setup_stream(monkeypatch)
    events = parsed(
        [frame async for frame in transport.answer_events(policy, scope, "Question", settings)]
    )
    assert events[-1]["code"] == "answer_unavailable"
    policy, scope, state, settings = setup_stream(monkeypatch, wait=True, timeout=0.01)
    events = parsed(
        [frame async for frame in transport.answer_events(policy, scope, "Question", settings)]
    )
    assert events[-1]["code"] == "request_timeout" and state.closed
    for error in [SQLAlchemyError("private"), TimeoutError()]:
        policy, scope, state, settings = setup_stream(monkeypatch, error=ValueError())
        monkeypatch.setattr(transport.AnswerHistory, "save", AsyncMock(side_effect=error))
        events = parsed(
            [frame async for frame in transport.answer_events(policy, scope, "Question", settings)]
        )
        assert events[-1]["code"] == "database_unavailable" and events[-1]["answer_id"] is None
    policy, scope, state, settings = setup_stream(
        monkeypatch, [AnswerResult(outcome="answered", text="Safe")]
    )
    monkeypatch.setattr(transport.AnswerHistory, "save", AsyncMock(side_effect=SQLAlchemyError()))
    events = parsed(
        [frame async for frame in transport.answer_events(policy, scope, "Question", settings)]
    )
    assert events[-1]["code"] == "database_unavailable"


@pytest.mark.anyio
async def test_heartbeat_then_cancellation_closes_work_and_saves_nothing(monkeypatch):
    policy, scope, state, settings = setup_stream(monkeypatch, wait=True)
    async with aclosing(transport.answer_events(policy, scope, "Question", settings)) as updates:
        assert await anext(updates) == ": keepalive\n\n"
    assert state.closed and policy.sessions.session.row is None


def test_route_preflight_contract_and_capabilities(monkeypatch):
    policy, scope, state, settings = setup_stream(
        monkeypatch, [AnswerResult(outcome="insufficient_evidence", text="No evidence")]
    )
    policy.require = AsyncMock()
    app = create_app()
    app.dependency_overrides[api.authorization] = lambda: policy
    monkeypatch.setattr(transport, "get_settings", lambda: settings)
    path = f"/v1/workspaces/{scope.tenant_id}/answers/stream"
    with TestClient(app) as client:
        assert client.post(path, json={"question": " "}).status_code == 422
        assert client.post(path, json={"question": "Q", "extra": True}).status_code == 422
        assert (
            client.post(path, json={"question": "Q"}, headers={"Last-Event-ID": "1"}).status_code
            == 409
        )
        response = client.post(path, json={"question": "Q"})
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert parsed([response.text])[-1]["type"] == "complete"
        cap = f"/v1/workspaces/{scope.tenant_id}/collections/{scope.collection_ids[0]}/capabilities"
        assert client.get(cap).json() == {"can_upload": True, "can_manage": True}
        policy.require.side_effect = AccessDenied(403, "denied")
        assert client.get(cap).json() == {"can_upload": False, "can_manage": False}
        policy.require.side_effect = AccessDenied(404, "not found")
        assert client.get(cap).status_code == 404
        policy.scope.side_effect = AccessDenied(401, "Select identity")
        assert client.post(path, json={"question": "Q"}).status_code == 401
    assert transport.error_message("missing_citations").startswith(
        "The answer could not be verified"
    )
    assert transport.error_message("database_unavailable").startswith(
        "The answer could not be saved"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("spec", ["2.0", "2.4"])
async def test_asgi_disconnect_cleans_up_producer_without_persistence(monkeypatch, spec):
    policy, scope, state, settings = setup_stream(
        monkeypatch, [AnswerProgress("generating")], wait=True
    )
    response = transport.ClosingStreamingResponse(
        transport.answer_events(policy, scope, "Q", settings)
    )
    sent = asyncio.Event()

    async def send(message):
        if message["type"] == "http.response.body":
            sent.set()
            if spec == "2.4":
                raise OSError("disconnected")

    async def receive():
        await sent.wait()
        return {"type": "http.disconnect"}

    try:
        await response({"type": "http", "asgi": {"spec_version": spec}}, receive, send)
    except Exception as error:
        assert type(error).__name__ == "ClientDisconnect"
    assert state.closed and policy.sessions.session.row is None


@pytest.mark.anyio
async def test_generation_resumes_after_a_heartbeat(monkeypatch):
    policy, scope = policy_fixture()

    async def delayed(*args):
        await asyncio.sleep(1.05)
        yield AnswerResult(outcome="insufficient_evidence", text="No usable evidence")

    @asynccontextmanager
    async def configured(settings):
        yield SimpleNamespace(stream=delayed)

    monkeypatch.setattr(transport, "configured_answer_service", configured)
    frames = [
        frame
        async for frame in transport.answer_events(policy, scope, "Q", Settings(_env_file=None))
    ]
    assert frames[0] == ": keepalive\n\n"
    assert parsed(frames)[-1]["type"] == "complete"


@pytest.mark.anyio
async def test_cleanup_failure_cannot_follow_a_success_terminal_event(monkeypatch):
    policy, scope = policy_fixture()

    async def stream(*args):
        yield AnswerResult(outcome="answered", text="Completed text")

    @asynccontextmanager
    async def configured(settings):
        yield SimpleNamespace(stream=stream)
        raise OSError("SDK cleanup failed")

    monkeypatch.setattr(transport, "configured_answer_service", configured)
    events = parsed(
        [
            frame
            async for frame in transport.answer_events(policy, scope, "Q", Settings(_env_file=None))
        ]
    )
    assert [event["type"] for event in events if event["type"] in {"complete", "error"}] == [
        "error"
    ]
    assert policy.sessions.session.row.result["outcome"] == "failed"
