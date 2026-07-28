"""FastAPI app factory + module-level ``app`` export."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from llmux.api.chat import chat_router
from llmux.api.health import health_router
from llmux.api.models import models_router
from llmux.config import Settings
from llmux.core.providers.registry import ProviderRegistry, build_providers
from llmux.observability.tracing import build_tracer, shutdown_tracer


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings if settings is not None else Settings()  # type: ignore[call-arg]

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        build_tracer(resolved)
        providers: ProviderRegistry | None = None
        try:
            providers = build_providers(resolved)
            app.state.providers = providers
            yield
        finally:
            if providers is not None:
                await providers.aclose()
            shutdown_tracer()

    app = FastAPI(title="LLMux", version=resolved.llmux_version, lifespan=lifespan)
    app.state.settings = resolved
    app.include_router(health_router, prefix="/v1")
    app.include_router(models_router, prefix="/v1")
    app.include_router(chat_router, prefix="/v1")
    return app


app = create_app()
