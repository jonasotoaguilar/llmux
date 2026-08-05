"""Anthropic provider adapter (httpx, non-streaming).

Implements the :class:`ProviderAdapter` port for the Anthropic Messages API
(``POST {base_url}/v1/messages``). ``complete_stream`` is out of scope and
raises ``NotImplementedError`` (streaming/SSE is explicitly deferred). The
HTTP client is injected so tests can supply ``httpx.MockTransport``;
production ownership is established by the registry in a later PR.

Translation rules (per the ``anthropic-provider`` spec):

* Auth: ``x-api-key`` + ``anthropic-version`` headers. ``Authorization`` is
  never used.
* System messages are extracted out of the ``messages`` array into a
  top-level ``system`` field; multiple system messages are joined with
  ``\\n\\n``; the system-message cache-control block is intentionally dropped
  (prompt caching is deferred).
* Unsupported roles (``tool``/``function``) raise :class:`ConfigurationError`.
* ``max_tokens`` defaults to ``1024`` when the caller omits it; a
  caller-supplied ``options["max_tokens"]`` overrides the default.
* Response ``type:"text"`` content blocks are joined in order; any non-text
  block (e.g. ``tool_use``) raises a sanitized :class:`UpstreamError`.
* ``usage.input_tokens`` -> ``prompt_tokens``;
  ``usage.output_tokens`` -> ``completion_tokens``.
* Only three stop-reason mappings are admitted: ``end_turn`` -> ``stop``,
  ``stop_sequence`` -> ``stop``, ``max_tokens`` -> ``length``.
* HTTP 4xx/5xx, transport errors, and timeouts are normalized to the
  existing :class:`LLMuxError` hierarchy. The upstream body is discarded
  (the safe envelope never leaks it).
* ``models()`` returns the configured model list; ``health()`` probes
  ``GET {base_url}/`` reachability only and MUST NOT perform an
  auth-validity probe (deferred).
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
#: Admitted Anthropic -> gateway stop-reason mappings (spec contract).
#: ``end_turn`` and ``stop_sequence`` both collapse to ``stop``; the only
#: non-stop admission is ``max_tokens`` -> ``length``.
_STOP_REASON_MAP: dict[str, str] = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
}
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
        return _parse_completion(data, default_model=model)

    def complete_stream(
        self,
        model: str,
        messages: Sequence[Mapping[str, object]],
        options: Mapping[str, object] | None = None,
    ) -> AsyncIterator[Chunk]:
        """Streaming is out of scope; raise ``NotImplementedError``."""
        raise NotImplementedError(
            "Anthropic streaming is out of scope; use complete() for non-streaming."
        )

    async def models(self) -> Sequence[ModelInfo]:
        """Return one ``ModelInfo`` per configured model."""
        return tuple(
            ModelInfo(id=m, provider=self.name, supports_streaming=False)
            for m in self._models
        )

    async def health(self) -> HealthStatus:
        """Probe reachability via ``GET {base_url}/`` only; no auth probe."""
        try:
            response = await self._client.get(f"{self._base_url}/")
        except httpx.HTTPError as exc:
            return HealthStatus(healthy=False, error=type(exc).__name__)
        return HealthStatus(healthy=response.status_code < 400, latency_ms=None)


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


def _parse_completion(data: object, *, default_model: str) -> CompletionResult:
    """Translate an Anthropic Messages response payload into a ``CompletionResult``."""
    if not isinstance(data, dict):
        raise UpstreamError("Anthropic response is not a JSON object")
    content_blocks = data.get("content")
    if not isinstance(content_blocks, list):
        raise UpstreamError("Anthropic response missing 'content' array")
    text_parts: list[str] = []
    for block in content_blocks:
        if not isinstance(block, dict):
            raise UpstreamError("Anthropic content block is not an object")
        block_type = block.get("type")
        if block_type != "text":
            # Non-text blocks (tool_use, image, etc.) are out of scope; reject
            # with only the block type — never the block's payload.
            raise UpstreamError(
                f"Anthropic returned a non-text content block: {block_type!r}",
                provider=_PROVIDER,
            )
        text = block.get("text")
        text_parts.append("" if text is None else str(text))
    usage_obj = data.get("usage")
    usage = usage_obj if isinstance(usage_obj, dict) else {}
    return CompletionResult(
        content="".join(text_parts),
        model=str(data.get("model", default_model)),
        prompt_tokens=_coerce_int(usage.get("input_tokens")),
        completion_tokens=_coerce_int(usage.get("output_tokens")),
        finish_reason=_map_stop_reason(data.get("stop_reason")),
        raw=data,
    )


def _coerce_int(value: object) -> int:
    """Coerce an arbitrary object into an int (default ``0`` on failure)."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _map_stop_reason(stop_reason: object) -> str:
    """Map an Anthropic ``stop_reason`` to the gateway finish reason.

    Only ``end_turn``/``stop_sequence`` -> ``stop`` and ``max_tokens`` ->
    ``length`` are admitted; other values pass through unchanged.
    """
    if stop_reason is None:
        return "stop"
    return _STOP_REASON_MAP.get(str(stop_reason), str(stop_reason))
