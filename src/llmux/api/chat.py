"""OpenAI-compatible ``/v1/chat/completions`` async handler.

Routes non-streaming requests through the router's ordered candidate
chain and returns a normalized 200 OpenAI-shaped completion envelope,
or one of the documented error envelopes (``400 ProviderSelectionError``
/ ``502 ConfigurationError`` / ``502 UpstreamError`` /
``504 UpstreamTimeoutError`` / ``503 AllProvidersFailedError``). An
explicit ``stream=true`` short-circuits to a JSON 501 *before* any
provider call or telemetry work, preserving the no-fake-SSE contract.
The public ``max_tokens`` field is forwarded to the selected adapter
through a fixed allowlist (:func:`_allowlist_options`); all other
arbitrary request extras are accepted by Pydantic but never reach a
provider.

Non-streaming requests attempt each selected candidate exactly once, in
configured order: first success wins; retryable failures advance; a
non-retryable typed error stops with its sanitized envelope; exhaustion
returns the sanitized 503 ``all_providers_failed`` envelope without
adding a synthetic telemetry hop.

Each attempt is wrapped in its own :class:`ChatCompletionTimer` that
records one ``chat.completion`` span and three bounded-cardinality
metrics (``requests_total`` counts attempts, ``errors_total``,
``duration_seconds``): a failed attempt on A followed by success on B
emits an error hop for A and a success hop for B. Selection misses use
the :data:`MODEL_UNKNOWN` sentinel so an unknown model never explodes
the time-series count. Errors set the span to
``Status(StatusCode.ERROR, error_type)`` with an ``error.type``
attribute; the description is the bounded label, never the raw
exception message or stack trace.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from llmux.core.errors import (
    AllProvidersFailedError,
    LLMuxError,
    is_retryable,
    to_openai_envelope,
)
from llmux.core.providers.base import CompletionResult
from llmux.core.providers.registry import ProviderRegistry
from llmux.core.router import select_candidates
from llmux.observability.metrics import (
    MODEL_UNKNOWN,
    PROVIDER_NONE,
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
    max_tokens: Annotated[int | None, Field(default=None, ge=1)]
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


def _allowlist_options(body: ChatCompletionRequest) -> dict[str, int]:
    """Return the admitted provider options for a chat request.

    The allowlist is the single forwarding contract between the public
    surface and the adapters: today only ``max_tokens`` is admitted.
    Unknown request extras remain accepted by Pydantic but are NEVER
    forwarded; omitting ``max_tokens`` passes no override, so the
    selected adapter applies its own default (``1024`` for Anthropic).
    """
    options: dict[str, int] = {}
    if body.max_tokens is not None:
        options["max_tokens"] = body.max_tokens
    return options


@chat_router.post("/chat/completions")
async def post_chat_completion(
    request: Request, body: ChatCompletionRequest
) -> JSONResponse:
    """Route a chat completion request to the selected provider.

    - ``stream`` explicitly ``True`` → 501 ``not_implemented`` JSON
      (no provider call, no telemetry, no SSE) — short-circuited
      BEFORE any telemetry timer is opened so the rejected path is
      never recorded (per the no-fake-SSE contract).
    - ``stream`` ``False`` (explicit or omitted → Pydantic default) →
      async ``select_candidates`` then a sequential attempt chain where
      each candidate's ``complete`` call runs inside its OWN
      :class:`ChatCompletionTimer`: first success returns the 200
      OpenAI-shaped envelope; retryable ``LLMuxError`` failures (see
      :func:`is_retryable`) record that attempt's error hop then
      advance; a non-retryable typed failure records and returns its
      sanitized envelope; exhaustion returns the sanitized 503
      ``AllProvidersFailedError`` envelope with no extra hop (every
      attempt already recorded one). A non-``LLMuxError`` exception is
      recorded by the attempt's timer as ``error.type=internal_error``
      and re-raised so FastAPI returns a 500.
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
    # 2. Pre-routing failures keep exactly one bounded hop with the
    #    provider=none / model=unknown sentinels: a missing registry
    #    (startup configuration fault) and a selection miss both return
    #    their sanitized envelope without touching any adapter.
    if registry is None:
        with telemetry.start(provider=None, model=MODEL_UNKNOWN) as timer:
            # Lifespan never ran (test harness without lifespan) —
            # treat as a startup configuration fault per the spec's
            # ConfigurationError mapping (502, never 400).
            from llmux.core.errors import ConfigurationError

            err = ConfigurationError("providers not initialized")
            timer.set_error_type(type(err).error_type)
            timer.mark_error()
            return _error_response(err)
    try:
        candidates = await select_candidates(body.model, registry)
    except LLMuxError as exc:
        # model label stays MODEL_UNKNOWN for selection miss so the
        # bounded set never sees the raw request model.
        with telemetry.start(provider=None, model=MODEL_UNKNOWN) as timer:
            timer.set_error_type(type(exc).error_type)
            timer.mark_error()
            return _error_response(exc)
    # 3. Sequential attempt chain: each candidate exactly once, in
    #    order, each attempt wrapped in its OWN ChatCompletionTimer so
    #    ``requests_total`` counts attempts and every hop carries its
    #    own provider/outcome/error.type. Retryable failures record an
    #    error hop then advance; terminal errors record and stop.
    for adapter in candidates:
        with telemetry.start(provider=None, model=MODEL_UNKNOWN) as timer:
            # ``name`` is not on the Protocol; PROVIDER_NONE keeps the
            # metric label bounded for adapters without it.
            timer.set_provider(getattr(adapter, "name", PROVIDER_NONE))
            # Request model BEFORE the call so an unexpected exception
            # still records a bounded model label.
            timer.set_model(body.model)
            try:
                result = await adapter.complete(
                    body.model,
                    [m.model_dump(exclude_none=True) for m in body.messages],
                    options=_allowlist_options(body),
                )
            except LLMuxError as exc:
                if is_retryable(exc):
                    # Record THIS attempt's error hop (failing
                    # provider, bounded error.type), then advance to
                    # the next candidate; the chain may still win.
                    timer.set_error_type(type(exc).error_type)
                    timer.mark_error()
                    continue
                timer.set_error_type(type(exc).error_type)
                timer.mark_error()
                return _error_response(exc)
            # Success: the model label is the canonical result model.
            timer.set_model(result.model)
            return JSONResponse(
                status_code=200,
                content=_completion_envelope(result),
                media_type="application/json",
            )
    # 4. Exhaustion: sanitized 503, no synthetic hop — every attempt
    #    already recorded its own error hop above.
    return _error_response(AllProvidersFailedError())


__all__: list[str] = ["chat_router", "post_chat_completion", "NOT_IMPLEMENTED_ERROR"]
