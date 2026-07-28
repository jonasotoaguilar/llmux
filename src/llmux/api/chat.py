"""OpenAI-compatible /v1/chat/completions 501 stub (no fake SSE)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

chat_router = APIRouter()

NOT_IMPLEMENTED_ERROR: dict[str, object] = {
    "error": {
        "message": "Chat completions are not implemented",
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


@chat_router.post("/chat/completions")
def post_chat_completion(_: ChatCompletionRequest) -> JSONResponse:
    return JSONResponse(status_code=501, content=NOT_IMPLEMENTED_ERROR)
