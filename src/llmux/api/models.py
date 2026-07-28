"""OpenAI-compatible /v1/models endpoint, aggregated from the provider registry."""

from __future__ import annotations

from fastapi import APIRouter, Request

from llmux.core.providers.registry import ProviderRegistry

models_router = APIRouter()


@models_router.get("/models")
async def list_models(request: Request) -> dict[str, object]:
    """Return one OpenAI-shaped model entry per (provider, model) in the registry."""
    registry: ProviderRegistry = request.app.state.providers
    data: list[dict[str, object]] = []
    for adapter in registry:
        for model in await adapter.models():
            data.append(
                {
                    "id": model.id,
                    "object": "model",
                    "created": 0,
                    "owned_by": model.provider,
                }
            )
    return {"object": "list", "data": data}
