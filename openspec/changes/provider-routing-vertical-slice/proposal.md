# Proposal: Provider Routing Vertical Slice — First Functional Provider Hop

> **Change**: `provider-routing-vertical-slice` · **Branch**: `feat/provider-routing-vertical-slice` (base `main` @ 02eade1, PR #8).
> **Delivery**: `auto-chain`, review budget 400 lines → three chained PRs. **Persistence**: hybrid (OpenSpec + Engram).
> No production code implemented at this phase.

## Intent

After `core-gateway-mvp`, the gateway still returns 501 at `POST /v1/chat/completions` and an empty list at `GET /v1/models`. Full ROADMAP Phase 1 (OpenAI + Anthropic + fallback + auth + metering) is too large for one 400-line-budget PR. This change ships the **smallest functional end-to-end provider hop**: one real OpenAI adapter, a priority router, a working non-streaming chat endpoint, a populated models endpoint, normalized errors/timeouts, and per-request telemetry. Anthropic and automatic fallback are deferred.

## Scope

### In Scope
- OpenAI `ProviderAdapter` (`httpx`, non-streaming) fulfilling ADR-0002's Protocol.
- Provider registry built from `Settings` at startup; priority router selecting first enabled adapter that lists the requested model.
- Real `POST /v1/chat/completions` (OpenAI-shaped envelope) for `stream=false`.
- `GET /v1/models` aggregated from configured providers.
- Normalized errors (OpenAI-shaped 400/502/504); httpx timeout → 504.
- Per-request OTel span + metrics (requests / errors / duration).
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODELS` / `OPENAI_TIMEOUT_S` env contract.

### Out of Scope (deferred, not dropped)
- Anthropic adapter → change `provider-anthropic-adapter`.
- Fallback / retry / circuit breaker → `provider-fallback-and-retries`.
- Streaming (`stream=true`) stays 501 → `chat-streaming`.
- API-key auth, metering persistence (PostgreSQL), rate limiting, admin dashboard.

## Capabilities

> Contract for `sdd-spec`. Researched against `openspec/specs/`.

### New Capabilities
- `provider-routing`: registry construction from `Settings` + priority router (first enabled adapter serving the model) + `LLMuxError` hierarchy (`ConfigurationError`, `ProviderSelectionError`, `UpstreamError`, `UpstreamTimeoutError`) with `.to_openai_envelope()`.
- `request-telemetry`: per `/v1/chat/completions` OTel span (`chat.completion`: model/provider/latency/tokens/error) + `chat_completion_{requests_total,errors_total,duration_seconds}`.

### Modified Capabilities
- `gateway-api-boundary`: `/v1/chat/completions` `stream=false` now returns 200 (real completion) or normalized 502/504 (no longer 501); `/v1/models` populated from configured providers; `stream=true` retains 501.
- `provider-abstraction`: `OpenAIAdapter` (httpx) marked `(implemented)` for `complete`/`models`/`health`; Protocol unchanged; `complete_stream` raises `NotImplementedError` (streaming deferred).

## Approach

Approach A (validated in exploration) — one change, **three chained PRs** under the 400-line budget; child PRs target `feat/provider-routing-vertical-slice` in chain order. Per ADR-0002 the Protocol is the contract; the registry is built once at startup on `app.state.providers`; the router consults it. No new ADR — ADR-0002 governs; router behavior is captured in `design.md`.

| PR | Scope | ~Lines |
|----|-------|--------|
| #1 | `Settings` `OPENAI_*`; `core/providers/openai.py`; `core/providers/registry.py`; tests vs `httpx.MockTransport` | 250–300 |
| #2 | `core/router.py` (priority select); real `GET /v1/models`; tests | 150–200 |
| #3 | real `POST /v1/chat/completions`; `core/errors.py` → 502/504; OTel span + metrics; tests | 250–300 |

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/llmux/config.py` | Modified | Add `OPENAI_*` fields; existing fields unchanged |
| `src/llmux/core/providers/openai.py` | New | `OpenAIAdapter` (httpx) |
| `src/llmux/core/providers/registry.py` | New | `build_providers(settings)` |
| `src/llmux/core/router.py` | New | `select_provider(model, providers)` |
| `src/llmux/core/errors.py` | New | `LLMuxError` hierarchy + envelopes |
| `src/llmux/api/chat.py` | Modified | async; real non-stream; OTel; 502/504 |
| `src/llmux/api/models.py` | Modified | aggregate from registry |
| `src/llmux/main.py` | Modified | `lifespan` builds providers |
| `src/llmux/observability/metrics.py` | New | 3 metrics |
| `tests/test_provider_routing_slice.py` | New | e2e vs `MockTransport` |
| `tests/test_unit_2.py` | Modified | invert 501/empty assertions; `stream=true` stays 501 |
| `.env.example` | Modified | add `OPENAI_*` |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Live OpenAI calls in CI | Med | Adapter accepts `httpx.AsyncClient`; tests inject `MockTransport` |
| Misconfigured provider (slug w/o key) now 502 vs silent skip | Low | Clear OpenAI-shaped 502; pre-MVP acceptable |
| OTel attribute drift (no prior consumer) | Med | Follow `gen_ai.*` conventions; simple `llmux.chat.duration` histogram first |
| 3-PR reviewer load | Med | `auto-forecast` chain; prior `core-gateway-mvp` precedent |

## Rollback Plan

Revert the three PRs in reverse chain order (#3 → #2 → #1); restore the `LLMUX_PROVIDERS_CONFIGURED`-only env contract. The prior 501 / empty-list contract remains in the archived `gateway-api-boundary` spec. **No schema or data migration to undo** — no persistence is introduced.

## Dependencies

- `httpx>=0.27.0` (already in `pyproject.toml`); `OPENAI_API_KEY` required when `openai` enabled.
- ADR-0002: `docs/adr/0002-provider-abstraction-pattern.md` (the Protocol this slice fulfills).

## Success Criteria

- [ ] `POST /v1/chat/completions` (`stream=false`) returns 200 vs a mocked OpenAI upstream; `stream=true` still 501.
- [ ] `GET /v1/models` returns ≥1 entry when `openai` configured; empty when not.
- [ ] Upstream 4xx/5xx → OpenAI-shaped 502; timeout → 504.
- [ ] Each `/v1/chat/completions` emits one OTel span + the 3 metrics.
- [ ] 3 PRs each ≤400 authored lines; `uv run pytest -q --cov=llmux --cov-fail-under=90` passes.
