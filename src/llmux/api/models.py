"""OpenAI-compatible ``GET /v1/models`` endpoint.

The endpoint sources its ``data`` array from the per-app
:class:`ProviderRegistry` stored on ``app.state.providers``. When no
registry is present (e.g. the test harness constructs an app without a
lifespan run), the response is an empty list. The list is ordered by the
registry's configured order: providers are visited in registration order,
and each provider's models are returned in their configured order — the
same order the registry uses to aggregate. ``created`` is a stable zero
per the OpenAI shape used by the rest of the slice.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from llmux.core.providers.registry import ProviderRegistry

models_router = APIRouter()


@models_router.get("/models")
async def list_models(request: Request) -> JSONResponse:
    """Return one OpenAI-shaped entry per configured ``(provider, model)``.

    Aggregation is delegated to :meth:`ProviderRegistry.models` so the
    registry remains the single source of truth for model ordering. When
    ``app.state.providers`` is missing the response is an empty list,
    matching the contract: zero providers → empty ``data``.
    """
    registry: ProviderRegistry | None = getattr(request.app.state, "providers", None)
    if registry is None:
        return JSONResponse(status_code=200, content={"object": "list", "data": []})
    aggregated = await registry.models()
    data = [
        {
            "id": m.id,
            "object": "model",
            "created": 0,
            "owned_by": m.provider,
        }
        for m in aggregated
    ]
    return JSONResponse(status_code=200, content={"object": "list", "data": data})
