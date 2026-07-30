"""Async priority router: first-match ``select_provider`` with no fallback.

The router walks the ordered :class:`ProviderRegistry` returned by
:func:`llmux.core.providers.registry.build_providers` and returns the first
adapter whose configured model list contains the requested model id. There is
no fallback, no retry, no weighted selection — if no provider offers the model,
:class:`ProviderSelectionError` (400) is raised. The lookup is ``O(N*M)`` where
``N`` is the number of providers and ``M`` is the per-provider model count; for
the configured one-digit provider and model list sizes in this slice that is
trivially fast, and avoids a per-request index allocation.

The router MUST be ``async`` so future PRs can introduce selection that needs
to query provider state (e.g. live health, weight tables) without changing
callers. The current implementation is awaitable but performs no I/O.
"""

from __future__ import annotations

from llmux.core.errors import ProviderSelectionError
from llmux.core.providers.base import ProviderAdapter
from llmux.core.providers.registry import ProviderRegistry


async def select_provider(model: str, registry: ProviderRegistry) -> ProviderAdapter:
    """Return the first provider in ``registry`` that offers ``model``.

    Selection is first-match in configured order. There is no fallback: when
    no provider offers the model, a :class:`ProviderSelectionError` is raised
    (mapped to HTTP 400 by ``to_openai_envelope``). The requested model id is
    intentionally NOT included in the raised error — the safe envelope never
    leaks caller input, and the spec's sanitization rule applies to error
    bodies only.
    """
    for adapter in registry.providers:
        models = await adapter.models()
        if any(m.id == model for m in models):
            return adapter
    raise ProviderSelectionError("Requested model is not available", model=model)
