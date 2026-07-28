"""OpenAI-compatible /v1/models endpoint (empty in this slice)."""

from __future__ import annotations

from fastapi import APIRouter

models_router = APIRouter()


@models_router.get("/models")
def list_models() -> dict[str, object]:
    return {"object": "list", "data": []}
