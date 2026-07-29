"""OpenTelemetry metric instruments for the LLMux chat-completion endpoint.

Exposes ``chat_completion_requests_total`` (Counter), ``chat_completion_errors_total``
(Counter), and ``chat_completion_duration_seconds`` (Histogram). Instruments are
created eagerly against the global ``MeterProvider`` so they are always
observable. When no SDK provider is installed, OTel returns no-op instruments.
Dimensions: ``provider``, ``model``, ``outcome``, optional ``error_type``.
"""

from __future__ import annotations

import time
from contextlib import AbstractContextManager
from typing import Any

from opentelemetry import metrics as otel_metrics

_INSTRUMENTATION_MODULE = "llmux"
_REQUEST_COUNTER = "chat_completion_requests_total"
_ERROR_COUNTER = "chat_completion_errors_total"
_DURATION_HISTOGRAM = "chat_completion_duration_seconds"
OUTCOME_SUCCESS = "success"
OUTCOME_ERROR = "error"
ERROR_TYPE_NONE = "none"
ERROR_TYPE_INTERNAL = "internal_error"
MODEL_UNKNOWN = "unknown"

_meter = otel_metrics.get_meter(_INSTRUMENTATION_MODULE)
_request_counter = _meter.create_counter(_REQUEST_COUNTER)
_error_counter = _meter.create_counter(_ERROR_COUNTER)
_duration_histogram = _meter.create_histogram(_DURATION_HISTOGRAM)


def record_chat_completion(
    *,
    provider: str,
    model: str,
    outcome: str,
    error_type: str | None,
    duration_seconds: float,
) -> None:
    """Record one ``/v1/chat/completions`` hop."""
    request_attrs: dict[str, str] = {
        "provider": provider,
        "model": model,
        "outcome": outcome,
        "error_type": error_type or ERROR_TYPE_NONE,
    }
    _request_counter.add(1, request_attrs)
    _duration_histogram.record(duration_seconds, {"provider": provider, "model": model})
    if outcome == OUTCOME_ERROR:
        _error_counter.add(1, request_attrs)


class ChatCompletionTimer(AbstractContextManager["ChatCompletionTimer"]):
    """Context manager that records the duration of a chat-completion hop."""

    __slots__ = ("_provider", "_model", "_start", "_outcome", "_error_type")

    def __init__(self, *, provider: str, model: str) -> None:
        self._provider = provider
        self._model = model
        self._start = 0.0
        self._outcome = OUTCOME_SUCCESS
        self._error_type: str | None = None

    def __enter__(self) -> ChatCompletionTimer:
        self._start = time.perf_counter()
        return self

    def set_provider(self, provider: str) -> None:
        """Update the provider label once selection succeeds."""
        self._provider = provider

    def set_model(self, model: str) -> None:
        """Update the model label once the canonical model is known."""
        self._model = model

    def mark_error(self, error_type: str) -> None:
        self._outcome = OUTCOME_ERROR
        self._error_type = error_type

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is not None and self._outcome == OUTCOME_SUCCESS:
            self._outcome = OUTCOME_ERROR
            self._error_type = ERROR_TYPE_INTERNAL
        record_chat_completion(
            provider=self._provider,
            model=self._model,
            outcome=self._outcome,
            error_type=self._error_type,
            duration_seconds=time.perf_counter() - self._start,
        )
        return None
