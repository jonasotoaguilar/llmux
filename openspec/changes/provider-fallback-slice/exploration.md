# Exploration: `provider-fallback-slice`

> **Change**: `provider-fallback-slice` (automatic cross-provider fallback in the OpenAI-compatible gateway).
> **Branch**: `feat/provider-fallback-slice` from `origin/main` @ `0eb5506` (post-Anthropic-adapter merge, PR #22).
> **Delivery**: `auto-chain`; session review budget `review_budget_lines: 800` (user-selected at session preflight). The SDD common guard's per-PR sizing default is 400 changed lines — that default constrains individual PR slices only, never the session budget; a single PR or a 2-PR chain both fit under the 800-line session budget.
> **Persistence**: hybrid (this file + Engram topic `sdd/provider-fallback-slice/explore`).
> **Architectural anchor**: ADR-0002 (`ProviderAdapter` Protocol) + ARCHITECTURE.md Router responsibilities ("manage fallback chain on failure"). **No new ADR** — this slice is a router-contract change already anticipated by ARCHITECTURE.md and ROADMAP Phase 1 ("Automatic fallback on 5xx / timeout / rate-limit").
> **RDD**: globally disabled; delivery stays `disabled/unmanaged`. `strict_tdd` is false.

## Quick path

1. Replace the first-match `select_provider` with candidate-ordered selection: `select_candidates(model, registry) -> tuple[ProviderAdapter, ...]` — every configured provider, in `LLMUX_PROVIDERS_CONFIGURED` order, that offers the requested model id. Empty tuple ⇒ `ProviderSelectionError` (400), exactly as today.
2. Make the chat handler attempt each candidate exactly once, first `CompletionResult` wins. After a retryable failure (`UpstreamTimeoutError`, or `UpstreamError` carrying `details["status"]` in {408, 429} or ≥500, or a transport `UpstreamError` with no status) continue to the next candidate; after a non-retryable failure stop and surface that error. If every candidate fails, return a sanitized 503 (`all_providers_failed`) — the one new `LLMuxError` subclass, aligned with ARCHITECTURE.md's "All providers unhealthy → 503".
3. Keep telemetry bounded: record **one hop per attempt** with the existing `ChatCompletionTimer` (the instruments already describe themselves as "per hop"); per-provider error rates stay truthful; `requests_total` now counts attempts, not requests — update the docstrings, not the schema. Optionally add a bounded `fallback_attempts` attribute (integer, bounded by provider count).
4. No config change: `LLMUX_PROVIDERS_CONFIGURED` is already the priority order. Fallback is default-on; no toggle, no per-request header, no health-state pre-selection, no same-provider retry/backoff, no circuit breaker, no model alias resolution — all deferred.
5. Modify the `provider-routing` spec's "First-Match Priority Provider Selection" requirement (its "no fallback" sentence and scenario are the contract this slice changes) and add a fallback capability block. The `gateway-api-boundary` spec needs no change unless the 503 addition is confirmed (see Open Questions).

## Current state (main @ 0eb5506)

| Area | State on main | Constraint this slice must respect |
|---|---|---|
| `src/llmux/core/router.py` | `async select_provider(model, registry)` — first adapter whose `await adapter.models()` contains the exact id; no fallback, no retry; raises `ProviderSelectionError` (400) on miss. Docstring explicitly says "no fallback". | The selection contract changes here. `select_provider`'s only production caller is `post_chat_completion`; the tests that call it directly are rewritten with it. Per the repo hard rule (remove obsolete paths, no compat layers) the first-match function is replaced, not wrapped. |
| `src/llmux/api/chat.py` | `stream=true` → 501 before any telemetry (unchanged); `ChatCompletionTimer` wraps ONE `select_provider` + ONE `adapter.complete`; `LLMuxError` → sanitized envelope; non-`LLMuxError` → `internal_error` metric + re-raise (500). | The 501 short-circuit, the no-registry → `ConfigurationError` (502) branch, the sanitized-envelope contract, and the `MODEL_UNKNOWN` sentinel for selection miss must all survive the attempt loop unchanged. |
| `src/llmux/core/errors.py` | `LLMuxError` base + `ConfigurationError`(502) / `ProviderSelectionError`(400) / `UpstreamError`(502) / `UpstreamTimeoutError`(504). `__init__(message, **details)` stores `details` on the instance but `to_openai_envelope` uses only class-level `safe_message` — details never reach the wire. | `UpstreamError` already carries the upstream HTTP status in `details["status"]` when raised from a non-2xx response; transport errors carry NO status. This is the raw material for retry eligibility — no adapter change needed for the classifier. |
| `src/llmux/core/providers/openai.py` / `anthropic.py` | Both: `httpx.TimeoutException` → `UpstreamTimeoutError`; other `httpx.HTTPError` → `UpstreamError` (no status); `response.status_code >= 400` → `UpstreamError` with `status` in details. So 429 and 5xx are currently conflated into `UpstreamError`(502), and Anthropic's HTTP 408 maps to `UpstreamError`, not `UpstreamTimeoutError` (a deviation from the Anthropic slice's exploration table). | The classifier must read `details["status"]` to distinguish 429/408/5xx (retryable) from other 4xx (not retryable). Optionally align the 408 mapping later; not required for this slice. |
| `src/llmux/observability/metrics.py` | Per-hop `ChatCompletionTimer`: one `chat.completion` span + 3 instruments; bounded labels `provider` ∈ {openai, anthropic, none}, `model`, `outcome` ∈ {success, error}, `error.type` ∈ {api_error, invalid_request_error, internal_error, none}; `set_provider`/`set_model`/`set_error_type`/`mark_error` set once per request. Metric description already says "per hop". | Fallback = N hops. Recording one timer per attempt keeps every hop's labels bounded and makes per-provider error accounting truthful (a failed attempt on provider A followed by success on B emits an error hop on A and a success hop on B). `ALLOWED_*` sets unchanged. |
| `src/llmux/core/providers/registry.py` | Ordered `RegistryEntry` tuple; `build_providers` fail-fast + transaction-like cleanup; `models()` aggregates in order; `aclose()` idempotent, closes factory-owned clients only. | No change. Registry order IS the fallback order. |
| `src/llmux/config.py` | `LLMUX_PROVIDERS_CONFIGURED` = ordered slug list (the router's priority order). | No new env. Fallback inherits this ordering. |
| Specs | `provider-routing` (delivered slice) "First-Match Priority Provider Selection": "Selection MUST be first-match with NO fallback … MUST NOT perform retries, backoff, or automatic failover" + scenarios asserting first-match and 400-on-miss. `provider-abstraction` non-goals list "router, or fallback selection" (port-level, unchanged). | The `provider-routing` requirement and its no-fallback scenario are MODIFIED by this slice's delta spec; the 400-on-miss scenario stays (empty candidates ⇒ `ProviderSelectionError`). |
| Tests | 81 tests; 97.97% coverage; `test_router_first_match_returns_priority_provider`, `test_router_no_match_raises_provider_selection_error`, `test_chat_502_on_upstream_error`, `test_chat_504_on_upstream_timeout`, `test_telemetry_bounded_label_values` (hard-coded bounded sets) directly encode first-match/no-fallback. | Router tests are rewritten; single-provider chat tests still pass (one candidate, all-failed ⇒ new envelope); bounded-set tests are extended with the new error type if 503 lands. |

### What the PRD/ARCHITECTURE mandate

- PRD acceptance: "Automatic failover to secondary provider on 5xx, timeout, or rate-limit." — retry eligibility is exactly {5xx, timeout, rate-limit}.
- ARCHITECTURE.md Router: "manage fallback chain on failure"; failure mode "All providers unhealthy → 503". — supports the 503 all-failed envelope.
- ROADMAP Phase 1 scope: "Automatic fallback on 5xx / timeout / rate-limit" — the original slice-7 plan in the archived core-gateway-mvp exploration (~300 ΔLoC, "stack on slice 6").

## Affected areas

| File | Action | Why |
|---|---|---|
| `src/llmux/core/router.py` | Modify | Replace `select_provider` with `select_candidates` (or add it and remove the obsolete function). One `models()` pass per provider per request, not per attempt. |
| `src/llmux/api/chat.py` | Modify | Attempt loop over candidates; per-attempt timer; first success wins; retryable vs non-retryable branch; all-failed envelope. 501 short-circuit and no-registry branch untouched. |
| `src/llmux/core/errors.py` | Modify (small) | Add `is_retryable(error: LLMuxError) -> bool` classifier (single source, exhaustively tested); add `AllProvidersFailedError` (503, `all_providers_failed`) if that option is chosen. |
| `src/llmux/observability/metrics.py` | Modify (small) | Docstring: `requests_total` semantics become per-attempt; optional bounded `fallback_attempts` attribute; `ALLOWED_*` sets extended with the new error type only if 503 lands. |
| `src/llmux/core/providers/openai.py`, `anthropic.py` | No change | Status already in `details`; classifier consumes it. (Optional follow-up: 408 → `UpstreamTimeoutError` in the Anthropic adapter.) |
| `tests/test_provider_routing_slice.py` | Modify | Rewrite router tests for `select_candidates`; add fallback matrix (5xx / timeout / 429 / 408 / transport / 4xx-no-fallback / all-failed / ordering / attempt count); extend bounded-telemetry tests. |
| `openspec/changes/provider-fallback-slice/specs/provider-routing/spec.md` | Create (delta) | MODIFY "First-Match Priority Provider Selection"; ADD fallback requirements + scenarios. |

## Approaches

| Decision | Option A (recommended) | Option B | Option C (rejected) |
|---|---|---|---|
| **Selection API** | `select_candidates(model, registry) -> tuple[ProviderAdapter, ...]` — all providers offering the model, in configured order; `select_provider` deleted (only caller is the handler; tests rewritten). Empty tuple ⇒ `ProviderSelectionError` (400) unchanged. | Keep `select_provider` (first) and add a separate `attempt_chain` in the handler that repeatedly calls it after each failure. | Keep `select_provider`; handler loops by re-selecting after each failure. |
| | Pros: one model-list pass per request; single deterministic contract; removes the now-false "no fallback" API; matches the repo rule against compat layers. Cons: two router tests rewritten (small). | Pros: smaller diff to `router.py`. Cons: re-querying `models()` per attempt is O(N·M) per attempt; leaves an obsolete first-match API that contradicts the new behavior. | Pros: none beyond B. Cons: same as B, plus hidden re-selection cost. |
| | **Chosen.** | Rejected. | Rejected. |
| **Retry eligibility** | Pure `is_retryable(error) -> bool` in `errors.py`: retryable = `UpstreamTimeoutError`; `UpstreamError` with `details["status"]` ∈ {408, 429} or ≥500; `UpstreamError` with no status (transport — ConnectError/ReadError ≈ provider unreachable). Non-retryable = `UpstreamError` with other 4xx status, `ProviderSelectionError`, `ConfigurationError`, unexpected exceptions. | Strict PRD literal: transport errors (no status) are NOT retryable; only 5xx/408/429/timeout. | Fold eligibility into a new `retryable: bool` field on `LLMuxError` subclasses. |
| | Pros: exhaustive, unit-testable, no adapter changes; a downed provider (connection refused) falls back — which is the whole point of failover. Cons: retrying on transport means the client may wait slightly longer before the final 503. | Pros: literal PRD compliance. Cons: a connect failure — the most common "provider down" signal — would NOT fail over, defeating the feature. | Pros: data on the class. Cons: every raise site must set it correctly; two sources of truth (class + instance); more churn for the same outcome. |
| | **Chosen.** Transport retry is a stated assumption for the proposal phase to confirm. | Rejected. | Rejected. |
| **All-candidates-failed response** | New `AllProvidersFailedError` (503, `error_type="api_error"`, code `all_providers_failed`), sanitized like every envelope. | Propagate the final attempt's error envelope unchanged (502/504). | 502 "upstream_error" always. |
| | Pros: matches ARCHITECTURE.md's documented "All providers unhealthy → 503"; deterministic regardless of which provider failed last; honest "service unavailable" semantics. Cons: one new error class + bounded-set/test update; clients that expect 502/504 must learn 503. | Pros: zero new classes; preserves the specific final failure (timeout vs upstream). Cons: the response depends on which provider happened to be last; 502 already means "upstream error" and is now ambiguous about "all upstreams failed"; ARCHITECTURE.md says 503. | Pros: none. Cons: lies about the cause. |
| | **Chosen.** Flagged as an open question (new public status code). | Alternative if 503 is rejected. | Rejected. |
| **Telemetry** | One `ChatCompletionTimer` hop PER ATTEMPT with the existing instruments; a failed attempt on provider A then success on B emits error-hop(A) + success-hop(B). Optional bounded `fallback_attempts` attribute (integer, ≤ provider count) on each hop. | Single request-level hop labeled with the final provider; attempts invisible; outcome=success if any attempt succeeded. | Nested spans: request parent + per-attempt children (parent span added). |
| | Pros: per-provider error rates stay truthful (the PRD's observability goal — hiding failed attempts would undercount errors on the failing provider); no new instruments; the metric contract already says "per hop"; bounded-cardinality preserved. Cons: `requests_total` now counts attempts — dashboard semantics change, must be documented. | Pros: "requests_total ≈ requests". Cons: failed attempts disappear from metrics — ops can't see the failing provider; requires new "did it fall back" signal to compensate. | Pros: clean trace topology. Cons: new parent-span machinery + a new span name; largest telemetry change; deferrable. |
| | **Chosen.** The per-hop language in the existing metric descriptions makes this the smallest truthful design. | Rejected. | Deferred to a future observability slice. |
| **Provider ordering / pre-selection** | Attempt candidates strictly in configured order; skip providers that don't offer the model; NO health-state pre-selection (no `health()` calls in the request path; `health()` is reachability-only and circuit breaking is deferred). | Skip a provider whose `health()` returned unhealthy in the last N seconds (in-memory cache). | Configurable per-provider fallback weights/lists. |
| | Pros: deterministic; zero per-request I/O beyond `models()` (pure, in-memory); smallest slice. Cons: a persistently down primary is retried on every request until a real circuit breaker lands (accepted — ARCHITECTURE.md lists circuit breakers as a future technique). | Pros: faster failover on known-down providers. Cons: async I/O + state + staleness on the hot path; `health()` reachability-only doesn't validate keys; scope creep. | Pros: expressive. Cons: config schema + validation + spec surface; YAGNI for MVP. |
| | **Chosen.** | Deferred. | Rejected. |
| **Config / request surface** | No new env, no headers, no toggle. `LLMUX_PROVIDERS_CONFIGURED` order = priority; fallback is default-on for retryable failures. | `LLMUX_FALLBACK_ENABLED` env toggle (default on). | Per-request opt-out header (e.g. `x-llmux-no-fallback`) or `fallback: false` body field. |
| | Pros: zero config churn; the PRD makes failover the expected behavior, not an opt-in. Cons: a platform engineer who wants single-provider strict behavior must remove the provider from config. | Pros: explicit off-switch. Cons: speculative config (repo rule: no speculative configuration); same result achievable by configuring one provider. | Pros: per-request control. Cons: expands the public API surface and the allowlist contract; deferrable to when a real need appears. |
| | **Chosen.** | Rejected. | Deferred. |
| **PR structure** | **Single PR** (~120 src + ~300 test lines ≈ 420 changed, within the 800-line session review budget) OR **2-PR chain**: PR1 router+errors+chat behavior; PR2 telemetry-doc/tests polish. | — | — |
| | Decision deferred to `sdd-tasks` forecast; both fit the 800-line session budget (`review_budget_lines: 800`). | | |

## Recommendation

Adopt Option A in every row above. Concretely:

1. **`select_candidates(model, registry) -> tuple[ProviderAdapter, ...]`** replaces `select_provider`; empty result ⇒ `ProviderSelectionError` (400) — selection-miss semantics unchanged, one `models()` pass per provider.
2. **Chat handler attempt loop**: for each candidate in order — run one `ChatCompletionTimer` hop, `adapter.complete(...)`; on `CompletionResult` → 200 envelope (stop); on retryable `LLMuxError` → record the error hop, continue; on non-retryable `LLMuxError` → record, return its envelope (stop); on unexpected exception → the timer records `internal_error` and re-raises (500, unchanged).
3. **`is_retryable()`** in `errors.py`: `UpstreamTimeoutError` ⇒ retryable; `UpstreamError` ⇒ retryable when `details["status"]` ∈ {408, 429} or ≥500, or when no status (transport); everything else non-retryable. Exhaustively parametrized tests.
4. **`AllProvidersFailedError` (503)** surfaced only when every candidate failed with retryable errors (or mixed — first non-retryable stops the chain, so 503 implies all attempts were retryable failures). Sanitized envelope, `ALLOWED_ERROR_TYPES` + bounded test updated.
5. **Telemetry**: one hop per attempt; docstrings updated ("requests_total counts non-streaming chat completion *attempts*"); optional `fallback_attempts` attribute on each hop; no new instruments; `ALLOWED_*` sets stay bounded.
6. **No config, no new deps, no ADR, no ARCHITECTURE.md change** (it already describes the fallback chain and the 503 failure mode). `gateway-api-boundary` spec unchanged unless 503 is confirmed (see Open Questions).
7. **Streaming stays 501**; `stream=true` short-circuit runs before any attempt. No same-provider retry/backoff, no health-state pre-selection, no circuit breaker, no alias resolution, no per-request opt-out, no persistence of failover events.

## Non-goals (explicit)

- Same-provider retry with backoff (failover only; backoff/circuit breaking are ARCHITECTURE.md-deferred techniques).
- Health-state-aware selection / skip-unhealthy (needs async hot-path I/O + staleness handling).
- Model alias resolution / canonical model mapping — the hard prerequisite for true OpenAI↔Anthropic failover with disjoint model ids; a follow-up `model-alias-federation` slice.
- Per-request fallback control (headers/body field) and a fallback enable toggle.
- Streaming fallback (`stream=true` remains 501).
- Logging upstream error bodies, persisting failover events, cost attribution of failed attempts.
- Any change to the `ProviderAdapter` port, the registry ownership model, or the `provider-abstraction` spec.

## Risks

- **Same-model-id limitation (high, design-level)**: OpenAI serves `gpt-*`, Anthropic serves `claude-*`; disjoint ids mean cross-provider fallback triggers in production only when operators configure overlapping model ids (e.g. a shared alias served by two OpenAI-compatible endpoints) or when a follow-up alias slice lands. The fallback MACHINERY is fully exercised and tested with overlapping ids; the GAP is model identity, not the router. The proposal must state this explicitly so the user can decide whether alias resolution moves into this slice.
- **`UpstreamError` conflation (medium)**: 4xx/429/5xx/transport all collapse into one class; `is_retryable` correctness depends on `details["status"]` being set by every non-2xx raise site (true today in both adapters) and on exhaustive parametrized tests. A future adapter that forgets the `status` detail would silently classify 401s as retryable transport errors — the classifier's no-status branch must be documented as "transport", and a RED test pins the adapter contract.
- **Non-idempotent retry (medium, accepted)**: a timed-out request may have completed server-side; falling back can duplicate generation and double-bill. Standard gateway trade-off; idempotency keys are ROADMAP Phase 3.
- **Telemetry semantics change (medium)**: `chat_completion_requests_total` becomes attempt-based; dashboards/alerts that assume one counter increment per HTTP request will under/over-count after fallback. Documented in the metric docstring + spec; per-provider error rates become MORE accurate.
- **New 503 status at the HTTP boundary (low-medium)**: the gateway currently returns only 400/502/504 for routed failures; 503 is new to clients. Mitigated by ARCHITECTURE.md precedent; alternative (last-error propagation) keeps the status set stable — open question for the user.
- **Test churn (low)**: two router tests + single-provider error-envelope tests are rewritten; the bounded-label test gains the new error type. Coordinated within one change; verified by the existing 90%-coverage + ruff + mypy gates.
- **No fallback if 4xx occurs early (low)**: a 401/404 on the primary stops the chain per strict PRD eligibility; a provider with a bad key does not fail over (correct per spec — auth faults are not availability faults). Documented in the spec.

## Dependencies

- No new runtime or test deps (httpx, pytest, OTel SDK already present).
- No ADR (ADR-0002 unchanged; the router's fallback responsibility is already in ARCHITECTURE.md).
- No `ARCHITECTURE.md` / `.env.example` / `config.py` change.
- Spec deltas: MODIFY `provider-routing` "First-Match Priority Provider Selection"; ADD `provider-fallback` requirements under the same capability (or a new `provider-fallback` capability — decide in spec phase).

## Open questions for the user (none block exploration)

1. **Model identity**: is same-model-id fallback acceptable for this slice (recommended), or must this slice also include minimal alias mapping so a `claude-*`-configured model can fail over from an OpenAI-requested id? (Adding aliases roughly doubles the slice.)
2. **All-failed envelope**: confirm the new 503 `all_providers_failed` (recommended, matches ARCHITECTURE.md) vs propagating the last attempt's 502/504.
3. **Transport errors**: confirm transport failures (connection refused, read errors — no HTTP status) are retryable (recommended) vs strict 5xx/timeout/rate-limit only.
4. **`fallback_attempts` attribute**: include the bounded attempt-count attribute on hops now (cheap) or defer.

## Ready for proposal

Yes. Hand off to `sdd-propose` with change name `provider-fallback-slice`. The proposal should:

- State the intent: failover to the next provider that offers the requested model id, on retryable failures only (5xx / 408 / 429 / timeout / transport), first success wins, all-failed ⇒ 503.
- Explicitly flag the same-model-id limitation and the three open questions above so the user decides before spec/design.
- Anchor on ADR-0002 (unchanged port) + ARCHITECTURE.md (Router fallback responsibility, 503 failure mode) + the delivered `provider-routing` spec whose no-fallback requirement this slice MODIFIES.
- Inherit the four reliability guardrails from the delivered slices (no test-client double-close, lifespan teardown order, bounded metric cardinality, no partial registry) — none of them are touched by this change; the bounded-label contract is preserved per-attempt.
- Forecast a single PR (~120 src + ~300 test lines ≈ 420 changed) or a 2-PR chain; both fit the 800-line session review budget (`review_budget_lines: 800`) — `sdd-tasks` decides.
- Defer streaming, backoff, circuit breaking, health-state pre-selection, alias resolution, per-request opt-out, and any adapter wire-shape changes.

**Do not implement code in this phase. Do not start, recover, validate, or fabricate any native review — review-driven development is OFF by user decision and delivery stays disabled/unmanaged under ordinary repository policy.**
