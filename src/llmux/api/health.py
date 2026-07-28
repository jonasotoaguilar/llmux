"""Gateway-native /v1/health endpoint (not OpenAI-compatible)."""

from __future__ import annotations

from fastapi import APIRouter, Request

health_router = APIRouter()


@health_router.get("/health")
def get_health(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "version": settings.llmux_version,
        "providers_configured": list(settings.llmux_providers_configured),
    }
