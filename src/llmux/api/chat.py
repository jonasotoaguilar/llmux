"""OpenAI-compatible ``/v1/chat/completions`` async handler.

Routes non-streaming requests to the provider selected by the configured
:mod:`llmux.core.router` and returns a normalized 200 OpenAI-shaped
completion envelope, or one of the documented error envelopes
(``400 ProviderSelectionError`` / ``502 ConfigurationError`` /
``502 UpstreamError`` / ``504 UpstreamTimeoutError``). An explicit
``stream=true`` short-circuits to a JSON 501 *before* any provider call
or telemetry work, preserving the no-fake-SSE contract.

Each non-streaming hop is wrapped in a :class:`ChatCompletionTimer` that
records one ``chat.completion`` span and three bounded-cardinality
metrics (``requests_total``, ``errors_total``, ``duration_seconds``).
Selection misses use the :data:`MODEL_UNKNOWN` sentinel so an unknown
model never explodes the time-series count. Errors set the span to
``Status(StatusCode.ERROR, error_type)`` with an ``error.type``
attribute; the description is the bounded label, never the raw
exception message or stack trace.
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
from llmux.observability.metrics import (
    MODEL_UNKNOWN,
    PROVIDER_NONE,
    ChatCompletionTimer,
    ChatTelemetry,
    NoopChatTelemetry,
)

chat_router = APIRouter()

NOT_IMPLEMENTED_ERROR: dict[str, object] = {
    "error": {
        "message": "Chat completions are not implemented",
        "type": "not_implemented_error",
        "param": None,
        "code": "not_implemented",
    },
}

_NOOP_TELEMETRY: NoopChatTelemetry = NoopChatTelemetry()


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
      (no provider call, no telemetry, no SSE) — short-circuited
      BEFORE the telemetry timer is opened so the rejected path is
      never recorded (per the no-fake-SSE contract).
    - ``stream`` ``False`` (explicit or omitted → Pydantic default) →
      async first-match ``select_provider`` then ``adapter.complete``
      wrapped in a :class:`ChatCompletionTimer`. 200 OpenAI-shaped
      envelope on success, sanitized ``LLMuxError`` envelope on typed
      failure. A non-``LLMuxError`` exception is caught by the timer,
      recorded as ``error.type=internal_error`` + ``Status(ERROR)``,
      then re-raised so FastAPI returns a 500.
    """
    # 1. Explicit stream=true short-circuit — MUST run before any
    #    telemetry work so the rejected path emits no span or metric.
    if body.stream is True:
        return JSONResponse(
            status_code=501,
            content=NOT_IMPLEMENTED_ERROR,
            media_type="application/json",
        )
    telemetry: ChatTelemetry | NoopChatTelemetry = getattr(
        request.app.state, "telemetry", _NOOP_TELEMETRY
    )
    registry: ProviderRegistry | None = getattr(request.app.state, "providers", None)
    # 2. Open the chat-completion timer. MODEL_UNKNOWN until selection
    #    resolves; the timer accepts the setters below to update the
    #    canonical post-routing provider/model/error_type.
    with telemetry.start(provider=None, model=MODEL_UNKNOWN) as timer:
        if not isinstance(timer, ChatCompletionTimer):
            # NoopChatTelemetry returns a different timer shape; both
            # expose the same setters, so the call shape is uniform.
            pass
        if registry is None:
            # Lifespan never ran (test harness without lifespan) —
            # treat as a startup configuration fault per the spec's
            # ConfigurationError mapping (502, never 400).
            from llmux.core.errors import ConfigurationError

            err = ConfigurationError("providers not initialized")
            timer.set_error_type(type(err).error_type)
            timer.mark_error()
            return _error_response(err)
        try:
            adapter = await select_provider(body.model, registry)
        except LLMuxError as exc:
            # model label stays MODEL_UNKNOWN for selection miss so the
            # bounded set never sees the raw request model.
            timer.set_error_type(type(exc).error_type)
            timer.mark_error()
            return _error_response(exc)
        # The Protocol does not require ``name`` (it would break
        # ``issubclass`` on ``runtime_checkable`` Protocols). The bounded
        # PROVIDER_NONE sentinel is the fallback for adapters that do
        # not expose ``name`` so the metric label never escapes the
        # bounded set.
        timer.set_provider(getattr(adapter, "name", PROVIDER_NONE))
        # The model label is the request model as soon as the router
        # has selected a provider. This MUST be set BEFORE the adapter
        # call so an unexpected (non-LLMuxError) exception bubbling
        # out of the adapter still records the request model on the
        # error metric — the bounded set stays bounded and
        # MODEL_UNKNOWN is reserved for the selection-miss branch.
        timer.set_model(body.model)
        try:
            result = await adapter.complete(
                body.model,
                [m.model_dump(exclude_none=True) for m in body.messages],
            )
        except LLMuxError as exc:
            timer.set_error_type(type(exc).error_type)
            timer.mark_error()
            return _error_response(exc)
        # On success the model label is the canonical result model
        # returned by the provider, not the request model.
        timer.set_model(result.model)
        return JSONResponse(
            status_code=200,
            content=_completion_envelope(result),
            media_type="application/json",
        )


__all__: list[str] = ["chat_router", "post_chat_completion", "NOT_IMPLEMENTED_ERROR"]
