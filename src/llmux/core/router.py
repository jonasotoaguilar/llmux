"""Async priority router: ordered ``select_candidates``.

The router walks the ordered :class:`ProviderRegistry` returned by
:func:`llmux.core.providers.registry.build_providers` and returns every
adapter whose configured model list contains the requested model id, in
configured order. The first matching provider is the primary candidate;
each later match is a fallback candidate for the chat attempt chain.
There is no retry, backoff, weighted selection, or health pre-selection —
if no provider offers the model, :class:`ProviderSelectionError` (400) is
raised. The lookup is ``O(N*M)`` where ``N`` is the number of providers
and ``M`` is the per-provider model count; for the configured one-digit
provider and model list sizes in this slice that is trivially fast, and
avoids a per-request index allocation.

The router MUST be ``async`` so future PRs can introduce selection that
needs to query provider state (e.g. live health, weight tables) without
changing callers. The current implementation is awaitable but performs no
I/O. The router emits no telemetry itself; the chat handler
(:mod:`llmux.api.chat`) records one bounded telemetry hop per attempt
over the returned candidates.
"""

from __future__ import annotations

from llmux.core.errors import ProviderSelectionError
from llmux.core.providers.base import ProviderAdapter
from llmux.core.providers.registry import ProviderRegistry


async def select_candidates(
    model: str, registry: ProviderRegistry
) -> tuple[ProviderAdapter, ...]:
    """Return every provider in ``registry`` that offers ``model``.

    Selection is exact-model in configured order: the first matching
    provider is the primary candidate and each later match is a fallback
    candidate. When no provider offers the model, a
    :class:`ProviderSelectionError` is raised (mapped to HTTP 400 by
    ``to_openai_envelope``). The requested model id is intentionally NOT
    included in the raised error — the safe envelope never leaks caller
    input, and the spec's sanitization rule applies to error bodies only.
    """
    candidates: list[ProviderAdapter] = []
    for adapter in registry.providers:
        models = await adapter.models()
        if any(m.id == model for m in models):
            candidates.append(adapter)
    if not candidates:
        raise ProviderSelectionError("Requested model is not available", model=model)
    return tuple(candidates)
