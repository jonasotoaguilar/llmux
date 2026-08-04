"""Ordered provider registry and transaction-like ``build_providers``.

The registry owns the production HTTP clients created during construction; it
closes them on :meth:`ProviderRegistry.aclose` (idempotent) or during the
transaction-like cleanup of :func:`build_providers` when a later provider
fails to construct. Adapters constructed with a caller-supplied client (e.g.
``MockTransport`` in tests) are recorded as ``client=None`` so the registry
never re-closes them.

Both supported slugs dispatch to their adapter constructor through the
``_build_openai`` / ``_build_anthropic`` helpers; every factory-created
client is appended to ``created_clients`` so one cleanup path serves all
providers.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass

import httpx

from llmux.config import Settings
from llmux.core.errors import ConfigurationError
from llmux.core.providers.anthropic import AnthropicAdapter
from llmux.core.providers.base import ModelInfo, ProviderAdapter
from llmux.core.providers.openai import OpenAIAdapter


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    """One adapter registered with the registry and the client it owns.

    ``client`` is the HTTP client the registry will close on
    :meth:`ProviderRegistry.aclose`. ``None`` means the adapter was
    constructed with a caller-owned client (e.g. a ``MockTransport``-backed
    client in tests) and the registry MUST NOT close it.
    """

    adapter: ProviderAdapter
    client: httpx.AsyncClient | None = None


class ProviderRegistry:
    """Ordered tuple of provider adapters with idempotent shutdown semantics."""

    def __init__(self, entries: tuple[RegistryEntry, ...]) -> None:
        self._entries = entries
        self._closed = False

    @property
    def providers(self) -> tuple[ProviderAdapter, ...]:
        """Return the ordered adapter tuple (immutable view)."""
        return tuple(entry.adapter for entry in self._entries)

    async def models(self) -> tuple[ModelInfo, ...]:
        """Aggregate one ``ModelInfo`` per provider × configured model."""
        out: list[ModelInfo] = []
        for entry in self._entries:
            out.extend(await entry.adapter.models())
        return tuple(out)

    async def aclose(self) -> None:
        """Close every registry-owned client. Idempotent and safe to repeat.

        Caller-owned clients (``RegistryEntry.client is None``) are NEVER
        closed by the registry; the caller retains responsibility for them.
        """
        if self._closed:
            return
        self._closed = True
        for entry in self._entries:
            if entry.client is not None:
                await entry.client.aclose()


ClientFactory = Callable[[], httpx.AsyncClient]


def _default_client_factory() -> httpx.AsyncClient:
    """Default production factory: a fresh ``httpx.AsyncClient()`` per call."""
    return httpx.AsyncClient()


def _build_openai(
    settings: Settings,
    client_factory: ClientFactory,
    created_clients: list[httpx.AsyncClient],
) -> RegistryEntry:
    """Construct the OpenAI entry for ``build_providers``.

    The factory-created client is appended to ``created_clients`` so the
    transaction-like cleanup closes it exactly once if a later provider
    fails to construct. The entry records the client as registry-owned.
    """
    if settings.openai_api_key is None:
        raise ConfigurationError(
            "OPENAI_API_KEY is required when 'openai' is enabled",
            missing_key="OPENAI_API_KEY",
            provider="openai",
        )
    client = client_factory()
    created_clients.append(client)
    adapter = OpenAIAdapter(
        client=client,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        models=tuple(settings.openai_models),
        timeout_s=settings.openai_timeout_s,
    )
    return RegistryEntry(adapter=adapter, client=client)


def _build_anthropic(
    settings: Settings,
    client_factory: ClientFactory,
    created_clients: list[httpx.AsyncClient],
) -> RegistryEntry:
    """Construct the Anthropic entry for ``build_providers``.

    Mirrors ``_build_openai``: the fail-fast key check, the factory-created
    registry-owned client, and the ``ANTHROPIC_*`` settings wiring.
    """
    if settings.anthropic_api_key is None:
        raise ConfigurationError(
            "ANTHROPIC_API_KEY is required when 'anthropic' is enabled",
            missing_key="ANTHROPIC_API_KEY",
            provider="anthropic",
        )
    client = client_factory()
    created_clients.append(client)
    adapter = AnthropicAdapter(
        client=client,
        api_key=settings.anthropic_api_key,
        base_url=settings.anthropic_base_url,
        version=settings.anthropic_version,
        models=tuple(settings.anthropic_models),
        timeout_s=settings.anthropic_timeout_s,
    )
    return RegistryEntry(adapter=adapter, client=client)


async def build_providers(
    settings: Settings,
    *,
    client_factory: ClientFactory = _default_client_factory,
) -> ProviderRegistry:
    """Build every configured provider in order with transaction-like cleanup.

    On any failure (duplicate slug, unknown slug, missing key, factory
    exception, or adapter-construction exception), every client already
    created by the factory is closed before the :class:`ConfigurationError`
    propagates. A successful return transfers ownership of every
    factory-built client to the registry exactly once; ``aclose()`` is
    idempotent and closes only those owned clients.
    """
    created_clients: list[httpx.AsyncClient] = []
    try:
        entries: list[RegistryEntry] = []
        seen: set[str] = set()
        for slug in settings.llmux_providers_configured:
            if slug in seen:
                raise ConfigurationError(
                    f"Provider '{slug}' is configured more than once",
                    slug=slug,
                )
            seen.add(slug)
            if slug == "openai":
                entries.append(_build_openai(settings, client_factory, created_clients))
            elif slug == "anthropic":
                entries.append(
                    _build_anthropic(settings, client_factory, created_clients)
                )
            else:
                raise ConfigurationError(
                    f"Unknown provider '{slug}'",
                    slug=slug,
                )
    except BaseException:
        for client in created_clients:
            with suppress(Exception):
                await client.aclose()
        raise
    return ProviderRegistry(tuple(entries))
