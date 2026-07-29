"""OpenAI-compatible ``/v1/chat/completions`` endpoint.

For ``stream=false`` the gateway calls the priority-selected provider, records
an OTel span + metrics, and returns an OpenAI-shaped completion envelope.
``stream=true`` returns 501 (no-fake-SSE contract). Errors map to OpenAI-shaped
400/502/504 envelopes; bodies never expose keys.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Annotated

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from opentelemetry import trace as otel_trace
from opentelemetry.trace import Span, Status, StatusCode
from pydantic import BaseModel, ConfigDict, Field

from llmux.core.errors import (
    ConfigurationError,
    LLMuxError,
    ProviderSelectionError,
    UpstreamError,
    UpstreamTimeoutError,
)
from llmux.core.providers.base import CompletionResult
from llmux.core.providers.registry import ProviderRegistry
from llmux.core.router import select_provider
from llmux.observability.metrics import MODEL_UNKNOWN, ChatCompletionTimer

chat_router = APIRouter()

_SPAN_NAME = "chat.completion"
_INSTRUMENTATION_MODULE = "llmux"

NOT_IMPLEMENTED_ERROR: dict[str, object] = {
    "error": {
        "message": "Chat completions streaming is not implemented",
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


def _build_completion_envelope(
    result: CompletionResult, *, request_id: str
) -> dict[str, object]:
    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": result.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result.content},
                "finish_reason": result.finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.prompt_tokens + result.completion_tokens,
        },
    }


def _error_response(
    err: LLMuxError, *, timer: ChatCompletionTimer, span: Span
) -> JSONResponse:
    timer.mark_error(err.error_type)
    span.set_attribute("error.type", err.error_type)
    span.set_status(Status(StatusCode.ERROR, err.error_type))
    return JSONResponse(status_code=err.status_code, content=err.to_openai_envelope())


@chat_router.post("/chat/completions")
async def post_chat_completion(
    body: ChatCompletionRequest, request: Request
) -> JSONResponse:
    if body.stream:
        return JSONResponse(status_code=501, content=NOT_IMPLEMENTED_ERROR)

    registry: ProviderRegistry = request.app.state.providers
    timer = ChatCompletionTimer(provider="none", model=body.model)
    started = time.perf_counter()
    tracer = otel_trace.get_tracer(_INSTRUMENTATION_MODULE)
    with (
        timer,
        tracer.start_as_current_span(_SPAN_NAME) as span,
    ):
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute("gen_ai.request.model", body.model)
        try:
            adapter = await select_provider(body.model, registry)
        except ProviderSelectionError as exc:
            timer.set_model(MODEL_UNKNOWN)
            return _error_response(exc, timer=timer, span=span)
        provider_name = str(getattr(adapter, "name", type(adapter).__name__).lower())
        timer.set_provider(provider_name)
        span.set_attribute("gen_ai.provider.name", provider_name)
        try:
            messages: list[Mapping[str, object]] = [
                {"role": m.role, "content": m.content} for m in body.messages
            ]
            result = await adapter.complete(body.model, messages)
        except (UpstreamTimeoutError, UpstreamError, ConfigurationError) as exc:
            return _error_response(exc, timer=timer, span=span)
        timer.set_model(result.model)
        span.set_attribute("gen_ai.response.model", result.model)
        span.set_attribute("gen_ai.usage.input_tokens", result.prompt_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", result.completion_tokens)
        span.set_attribute(
            "llmux.request.duration_ms",
            max(0.0, (time.perf_counter() - started) * 1000.0),
        )
        return JSONResponse(
            status_code=200,
            content=_build_completion_envelope(result, request_id="chatcmpl-local"),
        )
