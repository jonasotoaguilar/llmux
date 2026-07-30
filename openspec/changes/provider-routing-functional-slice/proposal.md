# Proposal: Provider Routing Functional Slice — First Functional Provider Hop

> **Change**: `provider-routing-functional-slice` · **Branch**: `feat/provider-routing-functional-slice` (base `origin/main` @ `02eade1`, PR #8). **Delivery**: `auto-chain` / `feature-branch-chain`, 400 authored lines/PR. **Anchor**: [ADR-0002](../../../docs/adr/0002-provider-abstraction-pattern.md) (`ProviderAdapter` protocol). **No new ADR** — this specializes one slice under the accepted pattern. **Persistence**: hybrid (OpenSpec + Engram `sdd/provider-routing-functional-slice/proposal`).

## Intent

Activate the `core-gateway-mvp` skeleton with the first real provider hop: route non-streaming OpenAI Chat Completions through a priority router, back `/v1/models` with configured models, and emit bounded OTel telemetry. Replaces the current 501 stubs and empty models list with functional behavior. Product outcome is identical to the blocked `provider-routing-vertical-slice` chain (PRs #10–#12), but with fresh artifacts and ledger, and the four review-discovered bugs baked in as design-time constraints rather than re-discovered at review.

## Scope

### In Scope
- OpenAI non-streaming adapter (injected `httpx.AsyncClient`); `complete_stream` raises `NotImplementedError`.
- Ordered startup `ProviderRegistry` with fail-fast `ConfigurationError` and `aclose()`.
- Async priority router: first-match `select_provider`; `ProviderSelectionError` (400) on no match.
- `LLMuxError` hierarchy → normalized OpenAI envelopes (400/502/504).
- `POST /v1/chat/completions` `stream=false` (default when field omitted): route + 200 envelope or 400/502/504; only explicit `stream=true` stays 501 (no-fake-SSE, no provider invocation, no telemetry).
- `GET /v1/models`: one entry per configured `(provider, model)`.
- One OTel span + three bounded-cardinality metrics per non-streaming hop.

### Out of Scope
- Anthropic; automatic fallback; retries/backoff; circuit breaking; real streaming/SSE.

## Capabilities

> Contract for `sdd-spec`. All work is `(planned)` — none of these files exist on `main` yet.

### New Capabilities
- `provider-routing`: first concrete provider (OpenAI non-streaming adapter) + ordered startup registry with fail-fast construction and `aclose()` + async first-match router (`ProviderSelectionError` on no match) + `LLMuxError` hierarchy mapping to normalized OpenAI error envelopes.

### Modified Capabilities
- `gateway-api-boundary`: `/v1/models` aggregates configured `(provider, model)` entries from the registry instead of an empty list; `/v1/chat/completions` with `stream=false` or omitted `stream` (treated as `stream=false`) routes to the selected provider and returns a 200 OpenAI envelope or normalized 400/502/504; only explicit `stream=true` retains the 501 no-fake-SSE contract (no provider invocation, no telemetry); each non-streaming hop emits bounded telemetry.

### Referenced, Unchanged
- `provider-abstraction`: the existing `ProviderAdapter` Protocol is satisfied by the new adapter — no contract change.

## Approach

Activate the ADR-0002 port with one concrete adapter behind a startup registry and an async priority router. FastAPI lifespan owns registry resources with fail-safe teardown; API handlers translate between OpenAI HTTP envelopes and normalized internal errors. Delivered as three chained PRs (Feature Branch Chain): PR1 → tracker branch, each child PR targets the previous branch, tracker → `main`.

## Three PR Boundaries (each ≤400 authored lines)

| PR | Scope | Estimate |
|----|-------|----------|
| **PR1** | config + `LLMuxError` hierarchy + OpenAI adapter + registry (`aclose`, fail-fast) | ~165 src + 8 tests |
| **PR2** | `select_provider` router + fail-safe lifespan + `/v1/models` aggregation | ~25 src + 6 tests |
| **PR3** | async chat handler (`stream=false` routed; `stream=true` 501) + span + 3 bounded metrics | ~110 src + 11 tests |

## Affected Areas

| Area | Impact | Change |
|------|--------|--------|
| `src/llmux/config.py` | Modified | OpenAI settings; fail-fast `ConfigurationError` on empty key/models/invalid URL |
| `src/llmux/core/errors.py` | New | `LLMuxError` + `ConfigurationError`/`ProviderSelectionError`/`UpstreamError`/`UpstreamTimeoutError` + `to_openai_envelope()` |
| `src/llmux/core/providers/{openai,registry}.py` | New | adapter + ordered registry / `build_providers` factory |
| `src/llmux/core/router.py` | New | first-match `select_provider` |
| `src/llmux/main.py` | Modified | fail-safe lifespan teardown order |
| `src/llmux/api/{chat,models}.py` | Modified | routed non-streaming path; registry-backed models |
| `src/llmux/observability/metrics.py` | New | `requests_total`, `errors_total`, `duration_seconds` (bounded labels) |
| `.env.example`, `tests/test_provider_routing_slice.py` | Modified/New | env contract; MockTransport + live-ASGI coverage |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Tracer startup leak (PR2) | Medium | Fail-safe teardown — see guardrail |
| Metric cardinality explosion (PR3) | Medium | `MODEL_UNKNOWN` on unselected models |
| Invisible OTel errors (PR3) | Low | `Status(ERROR, description)` + `error.type` attr |
| Test-client double-close (PR1) | Low | `aclose()` closes production clients only |

## Rollback Plan

Revert the three PRs in reverse order (PR3 → PR2 → PR1). Each is self-contained; reverting PR1 returns `main` to the 501-stub + empty-models baseline. No persistence or data migration is introduced, so rollback is a pure branch revert.

## Dependencies

- [ADR-0002](../../../docs/adr/0002-provider-abstraction-pattern.md) (Provider abstraction) — Accepted.
- Existing `src/llmux/observability/tracing.py` and `src/llmux/config.py` on `main`.

## Success Criteria

### Functional
- [ ] `stream=false` routes to OpenAI and returns a 200 OpenAI envelope.
- [ ] Selection miss (`ProviderSelectionError`) → 400; `ConfigurationError` surfaced at HTTP → 502 (normally fail-fast at startup); upstream error (`UpstreamError`) → 502; timeout (`UpstreamTimeoutError`) → 504; envelopes carry no keys, upstream payloads, or stack traces.
- [ ] Omitted `stream` defaults to `stream=false` and routes (200/400/502/504); only explicit `stream=true` returns 501, `application/json`, no SSE frames, no provider invocation, no telemetry.
- [ ] `/v1/models` returns one entry per configured `(provider, model)`.
- [ ] OpenAI enabled with empty key/models/invalid URL → startup `ConfigurationError`.
- [ ] `complete_stream` raises `NotImplementedError`; `select_provider` is first-match with no fallback.

### Reliability Guardrails (pre-discovered — MUST hold)
- [ ] **Fail-safe teardown**: on registry build failure inside the lifespan, `shutdown_tracer()` still runs; `aclose()` precedes tracer shutdown.
- [ ] **Bounded cardinality**: every metric label uses the `MODEL_UNKNOWN` constant when selection fails; no raw request `model` on unselected paths.
- [ ] **Stable OTel error status**: errors set `Status(StatusCode.ERROR, error_type)` + an `error.type` attribute, not a bare `OK`+attr side-channel.
- [ ] **Uncaught-exception accounting**: the routed call site catches every `LLMuxError` type — increments the error counter, sets span status, emits the envelope; no bare `except: pass`.
- [ ] **No test-client double-close**: `aclose()` closes only production clients; `MockTransport`-backed test clients stay caller-owned and are not re-closed.

### Delivery
- [ ] Three chained PRs, each ≤400 authored lines; child PRs target the previous branch; tracker targets `main`.
