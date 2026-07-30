"""OpenAI-compatible ``/v1/chat/completions`` async handler.

Routes non-streaming requests to the provider selected by the configured
:mod:`llmux.core.router` and returns a normalized 200 OpenAI-shaped
completion envelope, or one of the documented error envelopes
(``400 ProviderSelectionError`` / ``502 ConfigurationError`` /
``502 UpstreamError`` / ``504 UpstreamTimeoutError``). An explicit
``stream=true`` short-circuits to a JSON 501 *before* any provider call
or telemetry work, preserving the no-fake-SSE contract.

No telemetry is emitted in this PR — the bounded OTel span, the three
metrics, and the ``MODEL_UNKNOWN`` sentinel land in PR6.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from llmux.core.errors import LLMuxError, to_openai_envelope
from llmux.core.providers.base import CompletionResult
from llmux.core.providers.registry import ProviderRegistry
from llmux.core.router import select_provider

chat_router = APIRouter()

NOT_IMPLEMENTED_ERROR: dict[str, object] = {
    "error": {
        "message": "Chat completions are not implemented",
        "type": "not_implemented_error",
        "param": None,
        "code": "not_implemented",
    },
}


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: str
    content: str | list[dict[str, object]] | None = None


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str
    messages: Annotated[list[ChatMessage], Field(min_length=1)]
    stream: bool = False


def _completion_envelope(result: CompletionResult) -> dict[str, object]:
    """Shape a :class:`CompletionResult` as an OpenAI chat completion envelope.

    The raw upstream payload is the source of truth for fields like ``id``
    and ``choices``; this helper injects the OpenAI-required ``object``
    discriminator and a stable ``created`` timestamp (``0`` — the same
    convention the rest of the slice uses, e.g. ``/v1/models``).
    """
    body: dict[str, object] = dict(result.raw)
    body.setdefault("object", "chat.completion")
    body.setdefault("created", 0)
    return body


def _error_response(error: LLMuxError) -> JSONResponse:
    """Build a sanitized OpenAI error response from any ``LLMuxError``."""
    return JSONResponse(
        status_code=error.status_code,
        content=to_openai_envelope(error),
        media_type="application/json",
    )


@chat_router.post("/chat/completions")
async def post_chat_completion(
    request: Request, body: ChatCompletionRequest
) -> JSONResponse:
    """Route a chat completion request to the selected provider.

    - ``stream`` explicitly ``True`` → 501 ``not_implemented`` JSON
      (no provider call, no telemetry, no SSE).
    - ``stream`` ``False`` (explicit or omitted → Pydantic default) →
      async first-match ``select_provider`` then ``adapter.complete``;
      200 OpenAI-shaped envelope on success, sanitized ``LLMuxError``
      envelope on typed failure.
    """
    if body.stream is True:
        return JSONResponse(
            status_code=501,
            content=NOT_IMPLEMENTED_ERROR,
            media_type="application/json",
        )
    registry: ProviderRegistry | None = getattr(request.app.state, "providers", None)
    if registry is None:
        # Lifespan never ran (test harness without lifespan) — treat as
        # a startup configuration fault per the spec's ConfigurationError
        # mapping (502, never 400).
        from llmux.core.errors import ConfigurationError

        return _error_response(ConfigurationError("providers not initialized"))
    try:
        adapter = await select_provider(body.model, registry)
        result = await adapter.complete(
            body.model,
            [m.model_dump(exclude_none=True) for m in body.messages],
        )
    except LLMuxError as exc:
        return _error_response(exc)
    return JSONResponse(
        status_code=200,
        content=_completion_envelope(result),
        media_type="application/json",
    )


__all__: list[str] = ["chat_router", "post_chat_completion", "NOT_IMPLEMENTED_ERROR"]
