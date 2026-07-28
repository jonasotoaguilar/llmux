"""Provider registry: ordered startup construction from ``Settings``.

Order matches ``LLMUX_PROVIDERS_CONFIGURED``; unknown slugs, duplicate
slugs, empty keys/models, and invalid URLs all raise
:class:`ConfigurationError` at startup (fail-fast). The registry owns the
HTTP clients it created; injected test clients remain caller-owned.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator, Sequence
from typing import final

import httpx
from pydantic import SecretStr

from llmux.config import Settings
from llmux.core.errors import ConfigurationError
from llmux.core.providers.base import ProviderAdapter
from llmux.core.providers.openai import OpenAIAdapter


@final
class ProviderRegistry:
    """Ordered collection of enabled provider adapters."""

    __slots__ = ("_adapters", "_owned_clients")

    def __init__(
        self,
        adapters: Sequence[ProviderAdapter],
        *,
        owned_clients: Sequence[httpx.AsyncClient] = (),
    ) -> None:
        self._adapters: tuple[ProviderAdapter, ...] = tuple(adapters)
        self._owned_clients: tuple[httpx.AsyncClient, ...] = tuple(owned_clients)

    def __len__(self) -> int:
        return len(self._adapters)

    def __iter__(self) -> Iterator[ProviderAdapter]:
        return iter(self._adapters)

    def __getitem__(self, index: int) -> ProviderAdapter:
        return self._adapters[index]

    async def aclose(self) -> None:
        """Close every owned client. Safe to call more than once."""
        for client in self._owned_clients:
            with contextlib.suppress(Exception):
                await client.aclose()


def build_providers(settings: Settings) -> ProviderRegistry:
    """Construct a :class:`ProviderRegistry` from runtime settings."""
    seen: set[str] = set()
    adapters: list[ProviderAdapter] = []
    owned: list[httpx.AsyncClient] = []
    for slug in settings.llmux_providers_configured:
        if slug in seen:
            raise ConfigurationError(
                f"Duplicate provider slug in LLMUX_PROVIDERS_CONFIGURED: {slug!r}",
                provider=slug,
            )
        seen.add(slug)
        if slug == "openai":
            adapters.append(_build_openai_adapter(settings, owned_clients=owned))
        else:
            raise ConfigurationError(f"Unknown provider slug: {slug!r}", provider=slug)
    return ProviderRegistry(adapters, owned_clients=owned)


def _build_openai_adapter(
    settings: Settings, *, owned_clients: list[httpx.AsyncClient]
) -> OpenAIAdapter:
    api_key_value = settings.openai_api_key.get_secret_value()
    if not api_key_value:
        raise ConfigurationError(
            "OPENAI_API_KEY is required when 'openai' is enabled",
            missing_key="OPENAI_API_KEY",
            provider="openai",
        )
    if not settings.openai_models:
        raise ConfigurationError(
            "OPENAI_MODELS must list at least one model when 'openai' is enabled",
            provider="openai",
        )
    base_url = str(settings.openai_base_url).rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise ConfigurationError(
            f"OPENAI_BASE_URL must be an http(s) URL, got: {base_url!r}",
            provider="openai",
        )
    client = httpx.AsyncClient(
        base_url=base_url, timeout=httpx.Timeout(settings.openai_timeout_s)
    )
    owned_clients.append(client)
    return OpenAIAdapter(
        client=client,
        api_key=SecretStr(api_key_value),
        base_url=base_url,
        models=settings.openai_models,
        timeout_s=settings.openai_timeout_s,
    )
