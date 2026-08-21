# Proposal: Provider Fallback Slice

## Intent

Cross-provider fallback after the Anthropic adapter merge (PR #22). Today the router is first-match with NO fallback; any outage, rate-limit, or timeout is a hard failure. PRD and ARCHITECTURE.md (Router "manage fallback chain on failure"; "All providers unhealthy → 503") mandate this. ADR-0002 unchanged.

## Scope

### In Scope
- `select_candidates(model, registry)` replaces `select_provider`: all providers offering the model id in configured order; empty ⇒ `ProviderSelectionError` (400) unchanged.
- Attempt loop: first success wins; retryable ⇒ next candidate; non-retryable ⇒ stop; all-failed ⇒ sanitized 503 `AllProvidersFailedError`.
- `is_retryable()`: timeout; status ∈ {408, 429} or ≥500; transport (no status); else non-retryable.
- Telemetry: one hop per attempt; `requests_total` → "per attempt"; optional `fallback_attempts`.
- Delta spec: MODIFY `provider-routing`; ADD `provider-fallback`.

### Out of Scope
Alias federation, health-state pre-selection, circuit breakers, same-provider retry/backoff, streaming fallback, per-request controls, auth, metering, dashboards, adapter/registry changes.

## Capabilities

### New Capabilities
- `provider-fallback`: retry eligibility, ordered attempt chain, first-success-wins, all-failed 503 envelope, per-attempt telemetry.

### Modified Capabilities
- `provider-routing`: "First-Match Priority Provider Selection" — replace no-fallback sentence and first-match scenario with candidate-ordered selection (400-on-miss kept); fallback on retryable failures only.

## Approach

Candidate-ordered selection + attempt loop; single `is_retryable()` source; per-attempt hops; all-failed ⇒ 503. No config.

## Assumptions / Tradeoffs

- Same-model-id matching: OpenAI and Anthropic ids are disjoint (`gpt-*`/`claude-*`), so failover fires only with overlapping configured ids; machinery tested with overlapping ids.
- Transport failures ARE retryable: a connect-refused provider must fail over.
- 503 is new at the HTTP boundary; `requests_total` becomes attempt-based; per-provider error rates become more truthful.

## Affected Areas

- `src/llmux/core/router.py`: Modified: `select_provider` → `select_candidates`
- `src/llmux/api/chat.py`: Modified: attempt loop, per-attempt hops, 503
- `src/llmux/core/errors.py`: Modified: `is_retryable()`, `AllProvidersFailedError`
- `src/llmux/observability/metrics.py`: Modified: docstrings, `fallback_attempts`, bounded sets
- `tests/test_provider_routing_slice.py`: Modified: fallback matrix tests
- `openspec/changes/provider-fallback-slice/specs/`: New: MODIFY `provider-routing`; ADD `provider-fallback`

## Risks

- Med: missing `details["status"]` ⇒ 401 misclassified → exhaustive parametrized `is_retryable` tests
- Med: duplicate generation on timeout → accepted; idempotency keys Phase 3
- Med: telemetry semantics shift → docstring + spec note
- High: fallback never triggers with disjoint ids → documented; alias slice follow-up

## Rollback Plan

Git revert of the slice's PR merge (no config/env migration, no new deps, no schema change) restores first-match. Removing a provider from `LLMUX_PROVIDERS_CONFIGURED` restores strict single-provider behavior.

## Dependencies

None new (httpx, pytest, OTel present). ADR-0002 and ARCHITECTURE.md unchanged.

## Success Criteria

- [ ] Fallback matrix green: 5xx/408/429/timeout/transport fail over; other 4xx don't; all-failed ⇒ 503
- [ ] Candidates attempted in configured order, exactly once each
- [ ] Per-attempt hops: error-hop on failing provider, success-hop on winner
- [ ] Full suite ≥90% coverage + ruff + mypy pass
