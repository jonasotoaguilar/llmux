"""FastAPI app factory + module-level ``app`` export.

The lifespan owns the provider registry and the OpenTelemetry tracer. The
construction order is fixed: ``build_tracer`` first (always), then
``build_providers`` inside a try/finally so the tracer is shut down even when
provider construction raises. When construction succeeds, the registry's
``aclose()`` is invoked BEFORE ``shutdown_tracer()`` so the registry's owned
HTTP clients are closed before the tracer's exporter flushes; when
construction fails, the registry is the factory's responsibility (it cleans
up partial clients) and the lifespan only runs tracer shutdown.

There is no scenario in which ``aclose()`` runs on a registry that does not
own its clients — the registry is only assigned to ``app.state`` after
``build_providers`` returns a complete ``ProviderRegistry``, and the
factory's transaction-like cleanup path never returns a partial registry.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from llmux.api.chat import chat_router
from llmux.api.health import health_router
from llmux.api.models import models_router
from llmux.config import Settings
from llmux.core.providers.registry import (
    ProviderRegistry,
    build_providers,
)
from llmux.observability.tracing import build_tracer, shutdown_tracer


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings if settings is not None else Settings()  # type: ignore[call-arg]

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # The tracer is built unconditionally so a ConfigurationError from
        # build_providers does not leak the OTel provider registration.
        build_tracer(resolved)
        registry: ProviderRegistry | None = None
        try:
            registry = await build_providers(resolved)
        finally:
            # Close the registry BEFORE the tracer flushes so the tracer's
            # BatchSpanProcessor can record any closing span, and so we do
            # not double-close clients: the factory's BaseException cleanup
            # path closes partial clients and never returns a registry, so
            # ``registry`` here is either a complete ProviderRegistry
            # (whose clients it owns) or None (no clients to close).
            if registry is not None:
                await registry.aclose()
            shutdown_tracer()
        _app.state.providers = registry
        yield

    app = FastAPI(title="LLMux", version=resolved.llmux_version, lifespan=lifespan)
    app.state.settings = resolved
    app.include_router(health_router, prefix="/v1")
    app.include_router(models_router, prefix="/v1")
    app.include_router(chat_router, prefix="/v1")
    return app


app = create_app()
