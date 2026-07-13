import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from opsverse_api.db.models import RequestLedger
from opsverse_api.deps import get_chat_service, get_chat_service_ws
from opsverse_rag import ChatService, ChatTurn, SearchFilters
from opsverse_rag.chat import ChatDelta, ChatDone, ChatError, ChatEvent, ChatSources

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

MAX_IMAGE_B64_CHARS = 8_000_000  # ~6 MB decoded


class ChatRequest(BaseModel):
    query: str = Field(min_length=1)
    history: list[ChatTurn] = []
    k: int = Field(default=6, ge=1, le=20)
    filters: SearchFilters | None = None
    image_base64: str | None = Field(default=None, max_length=MAX_IMAGE_B64_CHARS)
    image_mime: str = "image/png"
    stream: bool = True


class ChatResponse(BaseModel):
    answer: str
    sources: ChatSources
    done: ChatDone | None = None
    error: str | None = None


async def _write_ledger(
    app, route: str, body: ChatRequest, done: ChatDone | None, error: str | None
) -> None:
    """Best-effort ledger row; never fails the response."""
    if error is not None:
        status = "error"
    elif done is not None and done.degraded:
        status = "degraded"
    else:
        status = "ok"
    try:
        async with app.state.db_sessionmaker() as session:
            session.add(
                RequestLedger(
                    route=route,
                    model=done.model if done else None,
                    status=status,
                    prompt_tokens=done.prompt_tokens if done else None,
                    completion_tokens=done.completion_tokens if done else None,
                    cost_usd=done.cost_usd if done else None,
                    latency_ms=done.latency_ms if done else None,
                    first_token_ms=done.first_token_ms if done else None,
                    meta={
                        "k": body.k,
                        "has_image": body.image_base64 is not None,
                        "degraded": done.degraded if done else [],
                        "cited": done.cited if done else [],
                        "error": error,
                    },
                )
            )
            await session.commit()
    except Exception:
        logger.exception("request_ledger write failed")


def _sse(event: ChatEvent) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


def _events(service: ChatService, body: ChatRequest):
    return service.stream_chat(
        body.query,
        history=body.history,
        k=body.k,
        filters=body.filters,
        image_b64=body.image_base64,
        image_mime=body.image_mime,
    )


@router.post("")
async def chat(
    body: ChatRequest,
    request: Request,
    service: Annotated[ChatService, Depends(get_chat_service)],
):
    events = _events(service, body)

    if body.stream:

        async def sse_stream():
            done: ChatDone | None = None
            error: str | None = None
            async for event in events:
                if isinstance(event, ChatDone):
                    done = event
                elif isinstance(event, ChatError):
                    error = event.message
                yield _sse(event)
            await _write_ledger(request.app, "/v1/chat", body, done, error)

        return StreamingResponse(
            sse_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Non-streaming: collect the same event stream into one JSON response.
    # The retrieval-eval and RAGAS harnesses use this mode.
    answer_parts: list[str] = []
    sources = ChatSources(sources=[])
    done: ChatDone | None = None
    error: str | None = None
    async for event in events:
        if isinstance(event, ChatSources):
            sources = event
        elif isinstance(event, ChatDelta):
            answer_parts.append(event.text)
        elif isinstance(event, ChatDone):
            done = event
        elif isinstance(event, ChatError):
            error = event.message
    await _write_ledger(request.app, "/v1/chat", body, done, error)
    return ChatResponse(answer="".join(answer_parts), sources=sources, done=done, error=error)


@router.websocket("/stream")
async def chat_stream(
    websocket: WebSocket,
    service: Annotated[ChatService, Depends(get_chat_service_ws)],
):
    """Multi-turn chat over one socket; supports image upload (base64).

    Client sends ChatRequest-shaped JSON; server replies with the same typed
    events as the SSE endpoint (sources / delta / done / error), then waits
    for the next request.
    """
    await websocket.accept()
    try:
        while True:
            payload = await websocket.receive_json()
            try:
                body = ChatRequest.model_validate(payload)
            except ValidationError as exc:
                await websocket.send_json(
                    {"type": "error", "message": f"invalid request: {exc.error_count()} errors"}
                )
                continue
            done: ChatDone | None = None
            error: str | None = None
            async for event in _events(service, body):
                if isinstance(event, ChatDone):
                    done = event
                elif isinstance(event, ChatError):
                    error = event.message
                await websocket.send_json(event.model_dump(mode="json"))
            await _write_ledger(websocket.app, "/v1/chat/stream", body, done, error)
    except WebSocketDisconnect:
        return
