"""Anthropic provider adapter (httpx, non-streaming).

Implements the :class:`ProviderAdapter` port for the Anthropic Messages API
(``POST {base_url}/v1/messages``). ``complete_stream`` is out of scope and
raises ``NotImplementedError``; the HTTP client is injected so tests can
supply ``httpx.MockTransport``.

Auth uses ``x-api-key`` + ``anthropic-version``; system messages are
extracted into a top-level ``system`` field (multiple messages joined
with ``\\n\\n``); unsupported roles raise :class:`ConfigurationError`;
``max_tokens`` defaults to ``1024`` unless overridden via options. HTTP
4xx/5xx, transport errors, and timeouts normalize to the existing
:class:`LLMuxError` hierarchy; the upstream body is discarded.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping, Sequence

import httpx
from pydantic import SecretStr

from llmux.core.errors import ConfigurationError, UpstreamError, UpstreamTimeoutError
from llmux.core.providers.base import (
    Chunk,
    CompletionResult,
    HealthStatus,
    ModelInfo,
)

DEFAULT_MAX_TOKENS: int = 1024
_ADMITTED_MESSAGE_ROLES: frozenset[str] = frozenset({"system", "user", "assistant"})
_SYSTEM_JOINER: str = "\n\n"
_PROVIDER: str = "anthropic"


class AnthropicAdapter:
    """ProviderAdapter implementation for the Anthropic Messages API."""

    name: str = "anthropic"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: SecretStr,
        base_url: str,
        version: str,
        models: Sequence[str],
        timeout_s: float,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._version = version
        self._models = tuple(models)
        self._timeout_s = timeout_s

    async def complete(
        self,
        model: str,
        messages: Sequence[Mapping[str, object]],
        options: Mapping[str, object] | None = None,
    ) -> CompletionResult:
        """POST to ``/v1/messages`` and return a ``CompletionResult``."""
        payload, system_text = _build_request(model, messages, options)
        headers = {
            "x-api-key": self._api_key.get_secret_value(),
            "anthropic-version": self._version,
            "Content-Type": "application/json",
        }
        if system_text is not None:
            payload["system"] = system_text
        try:
            response = await self._client.post(
                f"{self._base_url}/v1/messages",
                json=payload,
                headers=headers,
                timeout=self._timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("Anthropic request timed out") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError("Anthropic request failed") from exc
        if response.status_code >= 400:
            # Upstream body discarded; safe envelope never leaks it.
            raise UpstreamError(
                "Anthropic returned an error status",
                provider=self.name,
                status=response.status_code,
            )
        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise UpstreamError("Anthropic returned non-JSON body") from exc
        return CompletionResult(
            content="",
            model=model,
            prompt_tokens=0,
            completion_tokens=0,
            finish_reason="stop",
            raw=data,
        )

    def complete_stream(
        self,
        model: str,
        messages: Sequence[Mapping[str, object]],
        options: Mapping[str, object] | None = None,
    ) -> AsyncIterator[Chunk]:
        raise NotImplementedError(
            "Anthropic streaming is out of scope; use complete() for non-streaming."
        )

    async def models(self) -> Sequence[ModelInfo]:
        raise NotImplementedError("PR3")

    async def health(self) -> HealthStatus:
        raise NotImplementedError("PR3")


def _build_request(
    model: str,
    messages: Sequence[Mapping[str, object]],
    options: Mapping[str, object] | None,
) -> tuple[dict[str, object], str | None]:
    """Build the Anthropic Messages payload (without ``system``)."""
    system_text, filtered_messages = _extract_system(messages)
    payload: dict[str, object] = {
        "model": model,
        "messages": [dict(m) for m in filtered_messages],
        "max_tokens": _resolve_max_tokens(options),
    }
    return payload, system_text


def _extract_system(
    messages: Sequence[Mapping[str, object]],
) -> tuple[str | None, list[Mapping[str, object]]]:
    """Pop ``role:"system"`` entries; join with ``\\n\\n``; reject unsupported."""
    system_parts: list[str] = []
    filtered: list[Mapping[str, object]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            content = message.get("content")
            if not isinstance(content, str):
                raise ConfigurationError(
                    "Anthropic system message content must be a string",
                    provider=_PROVIDER,
                )
            system_parts.append(content)
            continue
        if role not in _ADMITTED_MESSAGE_ROLES:
            raise ConfigurationError(
                f"Anthropic does not support role '{role}'",
                invalid_role=str(role),
                provider=_PROVIDER,
            )
        filtered.append(message)
    if not system_parts:
        return None, filtered
    return _SYSTEM_JOINER.join(system_parts), filtered


def _resolve_max_tokens(options: Mapping[str, object] | None) -> int:
    """Return the caller-supplied ``max_tokens`` or the default ``1024``."""
    if options is None:
        return DEFAULT_MAX_TOKENS
    value = options.get("max_tokens")
    if isinstance(value, bool):
        # ``bool`` subclasses ``int``; treat as "no override".
        return DEFAULT_MAX_TOKENS
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return DEFAULT_MAX_TOKENS
    return DEFAULT_MAX_TOKENS
