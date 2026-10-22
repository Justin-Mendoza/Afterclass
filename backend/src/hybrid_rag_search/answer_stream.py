"""Request-owned answer streams: drafts, checked completion, and cancellation."""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing
from time import perf_counter
from typing import Annotated, Literal
from uuid import UUID

import anyio
from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from hybrid_rag_search.answer_history import AnswerHistory
from hybrid_rag_search.answers import (
    AnswerCitation,
    AnswerDraft,
    AnswerProgress,
    AnswerResult,
    configured_answer_service,
)
from hybrid_rag_search.api import DemoUser, Policy
from hybrid_rag_search.api_errors import APIError
from hybrid_rag_search.authorization import Authorization, AuthorizedScope
from hybrid_rag_search.config import Settings, get_settings

router = APIRouter(prefix="/v1/workspaces/{workspace_id}/answers", tags=["answers"])


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=4096)
    collection_id: UUID | None = None


class ProgressEvent(BaseModel):
    type: Literal["progress"] = "progress"
    stage: Literal["retrieving", "generating", "validating", "saving"]


class ContentEvent(BaseModel):
    type: Literal["content"] = "content"
    text: str


class CitationsEvent(BaseModel):
    type: Literal["citations"] = "citations"
    citations: tuple[AnswerCitation, ...]


class CompleteEvent(BaseModel):
    type: Literal["complete"] = "complete"
    answer_id: UUID
    result: AnswerResult


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str
    answer_id: UUID | None = None


StreamEvent = ProgressEvent | ContentEvent | CitationsEvent | CompleteEvent | ErrorEvent


def error_message(code: str) -> str:
    if code == "request_timeout":
        return "The answer took too long. Try again when you are ready."
    if code == "database_unavailable":
        return "The answer could not be saved. Please try again."
    if code in {"invalid_citation", "missing_citations", "invalid_answer_status", "empty_answer"}:
        return "The answer could not be verified. Please try again."
    return "The answer could not be completed. Please try again."


def encode_event(event: StreamEvent, sequence: int) -> str:
    # JSON is data, including newlines and text that looks like SSE framing.
    payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
    return f"id: {sequence}\nevent: {event.type}\ndata: {payload}\n\n"


async def answer_events(
    policy: Authorization, scope: AuthorizedScope, question: str, settings: Settings
) -> AsyncIterator[str]:
    """A bounded queue keeps provider work request-owned and permits heartbeats."""
    queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue(maxsize=16)
    started = perf_counter()
    first_content_ms: float | None = None
    history = AnswerHistory(policy)

    def with_timings(result: AnswerResult) -> AnswerResult:
        return result.model_copy(
            update={
                "configuration": {
                    **result.configuration,
                    "timings": {
                        "first_content_ms": first_content_ms,
                        "total_ms": (perf_counter() - started) * 1000,
                        "generation_ms": result.usage.get("latency_ms"),
                    },
                }
            }
        )

    async def failed(code: str) -> None:
        result = with_timings(AnswerResult(outcome="failed", text="", error_code=code))
        answer_id = None
        try:
            async with asyncio.timeout(5):
                answer_id = await history.save(scope, question, result)
        except (SQLAlchemyError, TimeoutError):
            code = "database_unavailable"
        await queue.put(ErrorEvent(code=code, message=error_message(code), answer_id=answer_id))

    async def produce() -> None:
        nonlocal first_content_ms
        try:
            async with asyncio.timeout(settings.answer_request_timeout_seconds):
                async with configured_answer_service(settings) as service:
                    final: AnswerResult | None = None
                    async with aclosing(service.stream(scope, question)) as updates:
                        async for update in updates:
                            if isinstance(update, AnswerProgress):
                                await queue.put(ProgressEvent(stage=update.stage))
                            elif isinstance(update, AnswerDraft):
                                if first_content_ms is None:
                                    first_content_ms = (perf_counter() - started) * 1000
                                await queue.put(ContentEvent(text=update.text))
                            else:
                                final = with_timings(update)
                if final is None:
                    raise ValueError("Missing terminal answer result")
                await queue.put(ProgressEvent(stage="saving"))
                answer_id = await history.save(scope, question, final)
                if final.outcome == "failed":
                    code = final.error_code or "answer_failed"
                    await queue.put(
                        ErrorEvent(code=code, message=error_message(code), answer_id=answer_id)
                    )
                else:
                    await queue.put(CitationsEvent(citations=final.citations))
                    await queue.put(CompleteEvent(answer_id=answer_id, result=final))
        except TimeoutError:
            await failed("request_timeout")
        except SQLAlchemyError:
            # A failed commit cannot be reported as a saved answer or retried implicitly.
            await queue.put(
                ErrorEvent(
                    code="database_unavailable", message=error_message("database_unavailable")
                )
            )
        except (OSError, ValueError):
            await failed("answer_unavailable")
        except Exception:
            # Never send provider exceptions, source text, or internal paths to the client.
            await failed("answer_failed")
        await queue.put(None)

    task = asyncio.create_task(produce())
    sequence = 0
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
            except TimeoutError:
                # Heartbeats also make ASGI 2.4 send-disconnects observable during model work.
                yield ": keepalive\n\n"
                continue
            if event is None:
                return
            sequence += 1
            yield encode_event(event, sequence)
    finally:
        task.cancel()
        # Starlette may cancel the consumer task group; still let the producer close its SDK.
        with anyio.CancelScope(shield=True):
            await asyncio.gather(task, return_exceptions=True)


class ClosingStreamingResponse(StreamingResponse):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # ASGI 2.4 send failures must also close the body iterator, not just the socket.
            if isinstance(self.body_iterator, AsyncGenerator):
                with anyio.CancelScope(shield=True):
                    await self.body_iterator.aclose()


@router.post(
    "/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Ordered SSE. Draft content is provisional until complete; no replay.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
    },
)
async def stream_answer(
    workspace_id: UUID,
    body: AnswerRequest,
    policy: Policy,
    demo_user: DemoUser = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    scope = await policy.scope(demo_user, workspace_id, body.collection_id)
    if last_event_id is not None:
        raise APIError(409, "resume_not_supported", "Answers cannot resume; start a new request.")
    return ClosingStreamingResponse(
        answer_events(policy, scope, body.question, get_settings()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
