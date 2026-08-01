# Proposal: Anthropic Provider Adapter Slice

> **Change**: `anthropic-provider-adapter-slice` (first slice of a new chain).
> **Delivery**: `auto-chain` / `feature-branch-chain`, 400-line review budget.
> **Persistence**: hybrid (this file + Engram `sdd/anthropic-provider-adapter-slice/proposal`).
> **Architectural anchor**: [ADR-0002](../../../docs/adr/0002-provider-abstraction-pattern.md) (`ProviderAdapter` Protocol). **No new ADR.**
> **Dependency**: `provider-routing-functional-slice` (PRs #10–#19, merged `12a32ae`) provides every shared component this slice plugs into.

## Intent

Deliver the second MVP provider (Anthropic) required by ROADMAP Phase 1: route non-streaming chat completions to Anthropic Claude models through the existing OpenAI-compatible surface. This activates a concrete implementation of the already-accepted `ProviderAdapter` pattern (ADR-0002) and is the prerequisite for the follow-up cross-provider fallback slice (`provider-fallback-and-retries`).

## Scope

### In Scope
- `AnthropicAdapter` over injected `httpx.AsyncClient`: `x-api-key` + `anthropic-version` headers, `POST {base_url}/v1/messages`, `complete_stream` → `NotImplementedError`.
- Messages-API translation: pop `system` messages → top-level `system`; default `max_tokens`=1024 when omitted; join `type:"text"` blocks; map `input/output_tokens` → `prompt/completion_tokens`; stop-reason map; non-text block → `UpstreamError`.
- Error normalization via existing `LLMuxError` hierarchy (no new classes); Anthropic error body discarded.
- `Settings` extension (`ANTHROPIC_*` env) + fail-fast `ConfigurationError` mirroring OpenAI.
- `build_providers` `"anthropic"` slug dispatch; transaction-like cleanup + `aclose()` ownership preserved.
- Configured model listing + reachability `health()` (`GET {base_url}/`); telemetry `provider` set grows by `"anthropic"`.
- `.env.example` update; mirrored tests in `tests/test_provider_routing_slice.py`.

### Out of Scope
Streaming/SSE, tool use, prompt caching, image/multimodal inputs, model alias resolution, cost tracking, auth-validity health probe, automatic fallback, retries/backoff/circuit breaking, new ADR, or ARCHITECTURE.md change.

## Capabilities

> Contract between proposal and specs phases. Researched against `openspec/specs/` + `provider-routing` delta.

### New Capabilities
- `anthropic-provider`: Concrete Anthropic Messages-API adapter contract — auth header pair, endpoint, system-message extraction, `max_tokens` default, response translation, token/stop-reason mapping, error normalization, configured model listing, reachability health.

### Modified Capabilities
- `provider-routing`: Provider configuration + fail-fast construction and the ordered registry now recognize the `"anthropic"` slug; lifecycle/ownership invariants and the first-match router (no fallback) are unchanged.

## Approach

Mirror the OpenAI slice (merged `12a32ae`): raw injected `httpx.AsyncClient`, no SDK, no new dep. 2-PR feature-branch chain on `feat/anthropic-provider-adapter-slice` from `main` @ `12a32ae`:
- **PR1** (~350 LoC): `config.py` Anthropic env + fail-fast validator; `core/providers/anthropic.py`; `.env.example`; adapter unit tests (protocol, success, request shape, system extraction, content join, stop-reason map, failure map, `models()`, `health()`).
- **PR2** (~250 LoC): `registry.py` slug dispatch; live-ASGI chat e2e (200/400/502/504/501) + lifespan behavior-first regression + bounded-telemetry set update.

## Affected Areas

| Area | Impact | Change |
|------|--------|--------|
| `src/llmux/core/providers/anthropic.py` | New | `AnthropicAdapter` |
| `src/llmux/config.py` | Modified | `ANTHROPIC_*` settings + validator |
| `src/llmux/core/providers/registry.py` | Modified | `"anthropic"` slug dispatch |
| `.env.example` | Modified | Anthropic env block |
| `tests/test_provider_routing_slice.py` | Modified | Mirrored test surface |

## Risks

| Risk | L | Mitigation |
|------|---|------------|
| `max_tokens` default truncates long output | Low | Caller override via `options["max_tokens"]`; documented |
| System cache-control lost on pop | Low | Prompt caching explicitly deferred |
| Raw httpx wire-shape drift | Low | `MockTransport` fixtures pin canonical Anthropic shapes |
| Test-client double-close regression | Low | `RegistryEntry(client=None)` + `_CountingClient.aclose_count==1` |
| PR1 lands but PR2 blocked (no chat path) | Low | Feature-branch-chain ordering; PR1 is the isolation surface |

## Reliability Guardrails (inherited from OpenAI slice)

Honored unchanged: (1) no test-client double-close; (2) lifespan teardown order (`aclose` after `yield`, before `shutdown_tracer`); (3) bounded metric cardinality; (4) no partial registry (fail-fast abort).

## Rollback Plan

Revert the 2 PRs → `main` returns to OpenAI-only (`12a32ae` state). No schema migrations, no persisted state, no required env beyond removing `ANTHROPIC_*`. The slice is purely additive — no shared component is structurally changed.

## Dependencies

- ADR-0002 (`ProviderAdapter` Protocol) — anchor; **no new ADR**.
- `provider-routing-functional-slice` (PRs #10–#19 @ `12a32ae`) — registry, router, `LLMuxError`, chat handler, telemetry, `/v1/models`.
- No new runtime/test deps.

## Success Criteria

- [ ] `POST /v1/chat/completions` with a configured Anthropic model → 200 OpenAI-shaped envelope (live ASGI).
- [ ] 400 selection miss / 502 upstream / 504 timeout sanitized; 501 no-telemetry on `stream=true`.
- [ ] Registry `aclose()` closes production client exactly once; lifespan invariant holds for the Anthropic entry.
- [ ] Bounded telemetry `provider` set includes `"anthropic"`; all tests + 90% coverage + ruff + mypy green.

## Proposal question round

`execution_mode=auto` — non-interactive, so questions are recorded for optional confirmation rather than blocking. Assumptions per the exploration's "Chosen" options: reachability-only health (`GET /`, not auth-validity); `max_tokens`=1024 caller-overridable; system messages joined `\n\n` and unsupported roles → `ConfigurationError` (502); non-text content blocks → `UpstreamError` (502); 2-PR feature-branch chain, each ≤400 authored lines.

Open product questions for optional confirmation (none block delivery):
1. Is `anthropic_default_max_tokens=1024` the right ceiling for the gateway's default workload, or should it be 2048/4096?
2. Should unsupported roles (`function`, `tool`) be 502 server-fault (chosen) or 400 caller-fault at the OpenAI public surface?
3. Is reachability-only health acceptable for ops dashboards before the fallback slice lands, or does Phase 1 need auth-validity probing sooner?
