"""Priority provider router: first-match selection by advertised model.

Iterates adapters in registry order and returns the first whose ``models()``
advertises the requested model. Raises :class:`ProviderSelectionError`
(status 400) when no enabled adapter serves the model. Automatic fallback,
retry, and circuit-breaking are intentionally deferred to
``provider-fallback-and-retries``.
"""

from __future__ import annotations

from llmux.core.errors import ProviderSelectionError
from llmux.core.providers.base import ProviderAdapter
from llmux.core.providers.registry import ProviderRegistry


async def select_provider(model: str, providers: ProviderRegistry) -> ProviderAdapter:
    """Return the first adapter in ``providers`` whose models include ``model``."""
    for adapter in providers:
        if any(m.id == model for m in await adapter.models()):
            return adapter
    raise ProviderSelectionError(
        f"No enabled provider serves model: {model!r}", model=model
    )
