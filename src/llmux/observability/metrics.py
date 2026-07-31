"""Bounded OpenTelemetry instrumentation for the chat completion hop.

Each non-streaming hop emits exactly one span (``chat.completion``) and
three instruments:

* ``chat_completion_requests_total`` — counter, incremented per hop
  (success or error). Labeled ``provider``, ``model``, ``outcome``,
  and (on error) ``error.type``.
* ``chat_completion_errors_total`` — counter, incremented on error
  only. Same labels as above.
* ``chat_completion_duration_seconds`` — histogram, recorded per hop
  in seconds. Same labels as the request counter.

Cardinality is bounded by the label-value sentinels below. A selection
miss MUST use the ``MODEL_UNKNOWN`` sentinel for the ``model`` label
(rather than the raw request model) so unknown-model traffic does not
explode the time-series count. A successful hop uses the canonical
result model returned by the provider's :class:`CompletionResult` so the
metric reflects what the upstream actually used.

Error accounting is enforced inside :class:`ChatCompletionTimer`. On
any :class:`LLMuxError` the timer records the bounded ``error.type``
and re-raises so the handler can return a sanitized envelope. On any
other (unexpected) exception the timer records the bounded
``internal_error`` label, sets the span to ``Status(StatusCode.ERROR)``,
and re-raises so the FastAPI exception handler returns a 500.

The telemetry owner accepts a ``Tracer`` and ``Meter`` so tests can
inject in-memory fakes (e.g. ``InMemorySpanExporter`` and
``InMemoryMetricReader``) via the public OpenTelemetry SDK without
mutating any private OTel global state.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import TYPE_CHECKING

from opentelemetry.metrics import Counter, Histogram, Meter
from opentelemetry.trace import Span, Status, StatusCode, Tracer

from llmux.core.errors import LLMuxError

if TYPE_CHECKING:
    from types import TracebackType

# --- Public stable names. Anything that flows onto a metric label or
# attribute MUST come from one of these sentinels. ----------------------------

SPAN_NAME: str = "chat.completion"

METRIC_REQUESTS_TOTAL: str = "chat_completion_requests_total"
METRIC_ERRORS_TOTAL: str = "chat_completion_errors_total"
METRIC_DURATION_SECONDS: str = "chat_completion_duration_seconds"

ATTR_PROVIDER: str = "provider"
ATTR_MODEL: str = "model"
ATTR_OUTCOME: str = "outcome"
ATTR_ERROR_TYPE: str = "error.type"

MODEL_UNKNOWN: str = "unknown"
PROVIDER_NONE: str = "none"  # selection miss / no registry
OUTCOME_SUCCESS: str = "success"
OUTCOME_ERROR: str = "error"
ERROR_TYPE_NONE: str = "none"  # only valid on the success branch
INTERNAL_ERROR_TYPE: str = "internal_error"  # bounded sentinel for unexpected errors

# Bounded set of allowed values for each label position. Tests consult
# these to assert that emitted metrics never escape the bounded set.
ALLOWED_OUTCOMES: frozenset[str] = frozenset({OUTCOME_SUCCESS, OUTCOME_ERROR})
ALLOWED_ERROR_TYPES: frozenset[str] = frozenset(
    {
        ERROR_TYPE_NONE,
        INTERNAL_ERROR_TYPE,
        # Class-level error_type values from core.errors.LLMuxError and
        # its subclasses. Kept in sync with src/llmux/core/errors.py.
        "api_error",
        "invalid_request_error",
    }
)


class ChatCompletionTimer:
    """Context manager that wraps one non-streaming chat completion hop.

    Created by :meth:`ChatTelemetry.start`. Callers update the
    provider/model/error_type via the ``set_*`` helpers between
    ``__enter__`` and ``__exit__`` so the recorded metric and span
    attributes reflect the canonical post-routing values. ``__exit__``
    records the request counter, the duration histogram, and (on
    error) the error counter + span status.
    """

    def __init__(
        self,
        telemetry: ChatTelemetry,
        *,
        provider: str | None,
        model: str,
    ) -> None:
        self._telemetry = telemetry
        self._provider: str | None = provider
        self._model: str = model
        self._error_type: str = ERROR_TYPE_NONE
        # ``_outcome_forced`` is set by :meth:`mark_error` when the
        # caller caught the LLMuxError itself and translated it to
        # an HTTP envelope (so the exception does not escape the
        # ``with`` block). When true, ``__exit__`` uses the error
        # outcome even though no exception is propagating.
        self._outcome_forced: bool = False
        # ``_span_cm`` is the OTel context-manager returned by
        # ``tracer.start_as_current_span``. Typed as
        # ``AbstractContextManager[Span]`` so mypy can verify the
        # ``__enter__``/``__exit__`` call shape.
        self._span_cm: AbstractContextManager[Span] | None = None
        self._span: Span | None = None
        self._start: float | None = None

    # --- Public mutators (called between __enter__ and __exit__) -------

    def set_provider(self, provider: str) -> None:
        """Set the canonical post-routing provider name (e.g. ``"openai"``)."""
        self._provider = provider
        if self._span is not None:
            self._span.set_attribute(ATTR_PROVIDER, provider)

    def set_model(self, model: str) -> None:
        """Set the canonical model label. On success this MUST be the
        result model from the :class:`CompletionResult`; on a post-routing
        error it MUST be the requested model (so the bounded set
        remains bounded and ``MODEL_UNKNOWN`` is reserved for the
        selection-miss branch)."""
        self._model = model
        if self._span is not None:
            self._span.set_attribute(ATTR_MODEL, model)

    def set_error_type(self, error_type: str) -> None:
        """Override the bounded ``error.type`` label for an
        :class:`LLMuxError` path. Should not be called for unexpected
        exceptions — those use :data:`INTERNAL_ERROR_TYPE` automatically."""
        self._error_type = error_type
        if self._span is not None:
            self._span.set_attribute(ATTR_ERROR_TYPE, error_type)

    def mark_error(self) -> None:
        """Mark the hop as errored.

        Called by the chat handler when it catches an
        :class:`LLMuxError` and translates it to a sanitized HTTP
        envelope (so the timer does not see the exception escape the
        ``with`` block). Sets the span status to
        ``Status(StatusCode.ERROR, error_type)`` and the
        ``outcome=error`` / ``error.type`` attributes eagerly, so APM
        backends see a complete errored span even when the HTTP
        envelope is the only public surface.

        Must be called AFTER :meth:`set_error_type`.
        """
        self._outcome_forced = True
        if self._span is None:
            return
        self._span.set_attribute(ATTR_OUTCOME, OUTCOME_ERROR)
        self._span.set_attribute(ATTR_ERROR_TYPE, self._error_type)
        self._span.set_status(Status(StatusCode.ERROR, self._error_type))

    # --- Context manager protocol ---------------------------------------

    def __enter__(self) -> ChatCompletionTimer:
        # record_exception=False, set_status_on_exception=False: the
        # SDK's automatic exception recording would attach the raw
        # exception message + stack trace to the span (which violates
        # the bounded sanitization contract) and would override the
        # status we set in __exit__. We handle both manually below
        # so the span status is always ``Status(ERROR, error_type)``
        # and only the bounded error.type attribute is recorded.
        self._span_cm = self._telemetry._tracer.start_as_current_span(
            SPAN_NAME,
            record_exception=False,
            set_status_on_exception=False,
        )
        self._span = self._span_cm.__enter__()
        self._start = time.perf_counter()
        # The provider label is ALWAYS set on enter (using the bounded
        # PROVIDER_NONE sentinel when no provider has been selected
        # yet) so the span attributes are present from the first
        # observation. Metrics and span attrs are the only public
        # observability surface; missing attrs would break APM queries
        # that filter on ``provider``.
        self._span.set_attribute(ATTR_PROVIDER, self._provider or PROVIDER_NONE)
        self._span.set_attribute(ATTR_MODEL, self._model)
        self._span.set_attribute(ATTR_ERROR_TYPE, ERROR_TYPE_NONE)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            assert self._span is not None
            assert self._span_cm is not None
            duration = time.perf_counter() - (self._start or 0.0)
            provider_label = self._provider or PROVIDER_NONE
            if exc is None and not self._outcome_forced:
                outcome = OUTCOME_SUCCESS
            else:
                outcome = OUTCOME_ERROR
                if isinstance(exc, LLMuxError):
                    # Trust the handler-set error_type; fall back to the
                    # class-level error_type if the handler did not set one.
                    if self._error_type == ERROR_TYPE_NONE:
                        self._error_type = type(exc).error_type
                elif exc is not None and self._error_type == ERROR_TYPE_NONE:
                    # Unexpected (non-LLMuxError) failure: bounded
                    # sentinel so the error counter never sees caller
                    # exception text.
                    self._error_type = INTERNAL_ERROR_TYPE
                # If the caller called :meth:`mark_error` (no exception
                # escaped), keep the explicitly-set error_type; do NOT
                # fall back to ERROR_TYPE_NONE.
            self._span.set_attribute(ATTR_OUTCOME, outcome)
            self._span.set_attribute(ATTR_ERROR_TYPE, self._error_type)
            if exc is not None:
                # The status description is the bounded error_type
                # (NOT the exception message) so the span never leaks
                # caller data. record_exception is intentionally NOT
                # called — it would attach the raw message and a
                # full stack trace, both of which can carry secrets.
                self._span.set_status(Status(StatusCode.ERROR, self._error_type))
            elif self._outcome_forced:
                # mark_error() already set the status; re-affirm so
                # __exit__ can be the single source of truth on the
                # outcome/error_type attribute pair.
                self._span.set_status(Status(StatusCode.ERROR, self._error_type))
            base_attrs: dict[str, str] = {
                ATTR_PROVIDER: provider_label,
                ATTR_MODEL: self._model,
            }
            if outcome == OUTCOME_SUCCESS:
                self._telemetry._requests.add(1, base_attrs)
                self._telemetry._duration.record(duration, base_attrs)
            else:
                error_attrs = {
                    **base_attrs,
                    ATTR_OUTCOME: OUTCOME_ERROR,
                    ATTR_ERROR_TYPE: self._error_type,
                }
                self._telemetry._requests.add(1, error_attrs)
                self._telemetry._errors.add(1, error_attrs)
                self._telemetry._duration.record(duration, error_attrs)
        finally:
            if self._span_cm is not None:
                self._span_cm.__exit__(exc_type, exc, tb)
        # Never swallow — let the chat handler or FastAPI decide the
        # HTTP mapping. Telemetry is already recorded at this point.
        return


class ChatTelemetry:
    """Owns the three chat-completion instruments and the span factory.

    Accepts a :class:`Tracer` and a :class:`Meter` (public OTel
    dependency injection) so production wires the global providers and
    tests wire in-memory fakes — no private OTel global mutation.
    """

    def __init__(self, *, tracer: Tracer, meter: Meter) -> None:
        self._tracer = tracer
        self._requests: Counter = meter.create_counter(
            METRIC_REQUESTS_TOTAL,
            description=(
                "Total non-streaming chat completion hops (success and error)."
            ),
        )
        self._errors: Counter = meter.create_counter(
            METRIC_ERRORS_TOTAL,
            description=(
                "Total non-streaming chat completion hops that ended in an error."
            ),
        )
        self._duration: Histogram = meter.create_histogram(
            METRIC_DURATION_SECONDS,
            unit="s",
            description=("Non-streaming chat completion hop duration in seconds."),
        )

    def start(
        self,
        *,
        provider: str | None = None,
        model: str = MODEL_UNKNOWN,
    ) -> ChatCompletionTimer:
        """Open a new chat completion span + metric timer."""
        return ChatCompletionTimer(self, provider=provider, model=model)


class NoopChatTelemetry:
    """Drop-in no-op for handlers that have no telemetry configured.

    Used by the bare-bones test harness (no lifespan) so the handler
    does not need a conditional branch. The returned timer accepts all
    setters and the context manager is a pass-through; nothing is
    recorded. Keep this in lock-step with the public surface of
    :class:`ChatTelemetry.start` so the handler's call shape does not
    diverge.
    """

    @contextmanager
    def start(
        self,
        *,
        provider: str | None = None,
        model: str = MODEL_UNKNOWN,
    ) -> Iterator[_NoopTimer]:
        yield _NoopTimer()


class _NoopTimer:
    """Drop-in no-op chat completion timer."""

    def set_provider(self, provider: str) -> None:  # noqa: ARG002 - API parity
        return None

    def set_model(self, model: str) -> None:  # noqa: ARG002 - API parity
        return None

    def set_error_type(self, error_type: str) -> None:  # noqa: ARG002 - API parity
        return None

    def mark_error(self) -> None:
        """Drop-in no-op for :meth:`ChatCompletionTimer.mark_error`."""
        return None


def build_chat_telemetry(*, tracer: Tracer, meter: Meter) -> ChatTelemetry:
    """Build a :class:`ChatTelemetry` from the given public OTel deps."""
    return ChatTelemetry(tracer=tracer, meter=meter)


__all__: list[str] = [
    "ATTR_ERROR_TYPE",
    "ATTR_MODEL",
    "ATTR_OUTCOME",
    "ATTR_PROVIDER",
    "ALLOWED_ERROR_TYPES",
    "ALLOWED_OUTCOMES",
    "ChatCompletionTimer",
    "ChatTelemetry",
    "ERROR_TYPE_NONE",
    "INTERNAL_ERROR_TYPE",
    "METRIC_DURATION_SECONDS",
    "METRIC_ERRORS_TOTAL",
    "METRIC_REQUESTS_TOTAL",
    "MODEL_UNKNOWN",
    "NoopChatTelemetry",
    "OUTCOME_ERROR",
    "OUTCOME_SUCCESS",
    "PROVIDER_NONE",
    "SPAN_NAME",
    "build_chat_telemetry",
]
