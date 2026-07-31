"""FastAPI app factory + module-level ``app`` export.

The lifespan owns the provider registry and the OpenTelemetry tracer. The
construction order is fixed: ``build_tracer`` first (always), then
``build_providers``. The registry's ``aclose()`` and ``shutdown_tracer()``
run AFTER ``yield`` on the successful-startup path so the registry's
owned HTTP clients stay open for the lifetime of request serving. When
construction raises, the factory's ``BaseException`` cleanup closes
partial clients, the lifespan runs ``shutdown_tracer()`` once, and the
exception is re-raised so the registry's ownership invariant (a registry
is only on ``app.state`` when complete) holds.

A :class:`ChatTelemetry` is built alongside the tracer and stored on
``app.state.telemetry`` so the chat handler can pick it up. The
telemetry owner accepts public OTel ``Tracer``/``Meter`` dependencies
(``build_chat_telemetry``) so tests can inject in-memory fakes
(``InMemorySpanExporter`` + ``InMemoryMetricReader``) without mutating
private OTel global state.

There is no scenario in which ``aclose()`` runs on a registry that does not
own its clients — the registry is only assigned to ``app.state`` after
``build_providers`` returns a complete ``ProviderRegistry``, and the
factory's transaction-like cleanup path never returns a partial registry.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry import metrics as otel_metrics

from llmux.api.chat import chat_router
from llmux.api.health import health_router
from llmux.api.models import models_router
from llmux.config import Settings
from llmux.core.providers.registry import (
    ProviderRegistry,
    build_providers,
)
from llmux.observability.metrics import build_chat_telemetry
from llmux.observability.tracing import build_tracer, shutdown_tracer

_TELEMETRY_INSTRUMENTATION_NAME = "llmux"


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings if settings is not None else Settings()  # type: ignore[call-arg]

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # The tracer is built unconditionally so a ConfigurationError from
        # build_providers does not leak the OTel provider registration.
        tracer = build_tracer(resolved)
        # Build the chat telemetry from the just-built tracer and the
        # global meter provider (which may be the SDK OTLP exporter in
        # production, or the noop provider in tests/dev). The
        # ``ChatTelemetry`` accepts public OTel dependencies, so this
        # can be re-pointed at in-memory fakes without private OTel
        # global mutation.
        meter = otel_metrics.get_meter(_TELEMETRY_INSTRUMENTATION_NAME)
        _app.state.telemetry = build_chat_telemetry(tracer=tracer, meter=meter)
        registry: ProviderRegistry | None = None
        started = False
        try:
            try:
                registry = await build_providers(resolved)
            except BaseException:
                # Build-failure path: the factory's ``except BaseException``
                # cleanup already closed every partial client, so only
                # tracer shutdown remains. ``started`` stays False so the
                # outer finally does not re-run shutdown_tracer or try to
                # close a registry the factory never returned.
                shutdown_tracer()
                raise
            _app.state.providers = registry
            started = True
            yield
        finally:
            # Success path: the registry owns its clients and MUST stay
            # open while serving requests, so the aclose + tracer
            # shutdown that previously ran before ``yield`` is deferred
            # until the lifespan exits. ``registry`` is a complete
            # ``ProviderRegistry`` here (``build_providers`` either
            # returned one or raised).
            if started:
                if registry is not None:
                    await registry.aclose()
                shutdown_tracer()

    app = FastAPI(title="LLMux", version=resolved.llmux_version, lifespan=lifespan)
    app.state.settings = resolved
    app.include_router(health_router, prefix="/v1")
    app.include_router(models_router, prefix="/v1")
    app.include_router(chat_router, prefix="/v1")
    return app


app = create_app()
