"""OpenAI provider adapter (httpx, non-streaming).

Implements the :class:`ProviderAdapter` port for the OpenAI chat completions
API. ``complete_stream`` is deferred to the ``chat-streaming`` change and
raises :class:`NotImplementedError`. The HTTP client is injected so tests
can supply :class:`httpx.MockTransport`; the registry owns production clients.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping, Sequence

import httpx
from pydantic import SecretStr

from llmux.core.errors import UpstreamError, UpstreamTimeoutError
from llmux.core.providers.base import (
    Chunk,
    CompletionResult,
    HealthStatus,
    ModelInfo,
)


class OpenAIAdapter:
    """ProviderAdapter implementation for the OpenAI HTTP API."""

    name: str = "openai"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: SecretStr,
        base_url: str,
        models: Sequence[str],
        timeout_s: float,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._models = tuple(models)
        self._timeout_s = timeout_s

    async def complete(
        self,
        model: str,
        messages: Sequence[Mapping[str, object]],
        options: Mapping[str, object] | None = None,
    ) -> CompletionResult:
        payload: dict[str, object] = {
            "model": model,
            "messages": [dict(m) for m in messages],
            "stream": False,
        }
        if options:
            payload.update(dict(options))
        headers = {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}
        url = f"{self._base_url}/chat/completions"
        try:
            response = await self._client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("OpenAI request timed out") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(f"OpenAI request failed: {exc!r}") from exc
        if response.status_code >= 400:
            raise UpstreamError(
                f"OpenAI returned status {response.status_code}",
                provider=self.name,
                status=response.status_code,
            )
        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise UpstreamError("OpenAI returned non-JSON body") from exc
        return _parse_completion(data, default_model=model)

    def complete_stream(
        self,
        model: str,
        messages: Sequence[Mapping[str, object]],
        options: Mapping[str, object] | None = None,
    ) -> AsyncIterator[Chunk]:
        """Streaming is deferred to the ``chat-streaming`` change."""
        raise NotImplementedError(
            "OpenAI streaming is deferred; use complete() for non-streaming calls."
        )

    async def models(self) -> Sequence[ModelInfo]:
        return tuple(
            ModelInfo(id=m, provider=self.name, supports_streaming=False)
            for m in self._models
        )

    async def health(self) -> HealthStatus:
        try:
            response = await self._client.get(f"{self._base_url}/models")
        except httpx.HTTPError as exc:
            return HealthStatus(healthy=False, error=str(exc))
        return HealthStatus(healthy=response.status_code < 400, latency_ms=None)


def _parse_completion(data: object, *, default_model: str) -> CompletionResult:
    if not isinstance(data, dict):
        raise UpstreamError("OpenAI response is not a JSON object")
    choices = data.get("choices")
    first = choices[0] if isinstance(choices, list) and choices else None
    if not isinstance(first, dict):
        raise UpstreamError("OpenAI response missing 'choices[0]'")
    message = first.get("message")
    if not isinstance(message, dict):
        raise UpstreamError("OpenAI 'choices[0].message' is not an object")
    usage_obj = data.get("usage")
    usage = usage_obj if isinstance(usage_obj, dict) else {}
    content = message.get("content")
    return CompletionResult(
        content="" if content is None else str(content),
        model=str(data.get("model", default_model)),
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
        completion_tokens=int(usage.get("completion_tokens", 0)),
        finish_reason=str(first.get("finish_reason") or "stop"),
        raw=data,
    )
