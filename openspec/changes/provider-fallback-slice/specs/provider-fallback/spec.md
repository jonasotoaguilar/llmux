# provider-fallback Specification

> **(planned)** Specializes ADR-0002 and ARCHITECTURE.md Router fallback responsibility; new error: `AllProvidersFailedError` (503).

## Purpose

Cross-provider failover: ordered attempts, first success wins, retryable failures advance, all-failed returns sanitized 503.

## Requirements

### Requirement: Retry Eligibility Classification (planned)

The system MUST expose `is_retryable(error)`. `UpstreamTimeoutError` MUST be retryable. `UpstreamError` MUST be retryable when `details["status"]` is 408, 429, or >= 500, and MUST be retryable when `details` has no status (transport). Everything else — other 4xx `UpstreamError`, `ProviderSelectionError`, `ConfigurationError`, unexpected exceptions — MUST be non-retryable.

#### Scenario: Timeout is retryable

- GIVEN the primary candidate raised `UpstreamTimeoutError`
- WHEN `is_retryable` classifies it
- THEN it is retryable

#### Scenario: Rate limit and server errors are retryable

- GIVEN an `UpstreamError` with `details["status"]` 429 or 503
- WHEN `is_retryable` classifies it
- THEN it is retryable

#### Scenario: Transport failure without status is retryable

- GIVEN an `UpstreamError` with no `details["status"]`
- WHEN `is_retryable` classifies it
- THEN it is retryable

#### Scenario: Auth and client errors are non-retryable

- GIVEN an `UpstreamError` with `details["status"]` 401 or 404
- WHEN `is_retryable` classifies it
- THEN it is NOT retryable

### Requirement: Ordered Attempt Chain (planned)

The chat handler MUST attempt each candidate exactly once, in configured order, until a `CompletionResult` is produced; the first success MUST win (200 envelope). Retryable failures MUST advance; non-retryable failures MUST stop, surfacing their envelope; exhausted candidates MUST return the sanitized 503 envelope (OpenAI-shaped, `all_providers_failed`, no keys, upstream bodies, or stack traces). The handler MUST NOT re-attempt candidates, issue concurrent duplicates, or retry the same provider.

#### Scenario: First success wins

- GIVEN candidates A then B, and A succeeds
- WHEN the attempt chain runs
- THEN the 200 envelope is returned
- AND B is never attempted

#### Scenario: Retryable failure falls back

- GIVEN A fails with a 5xx and B succeeds
- WHEN the attempt chain runs
- THEN B's result is returned as 200
- AND each candidate is attempted exactly once

#### Scenario: Non-retryable failure stops the chain

- GIVEN A fails with a 401
- WHEN the attempt chain runs
- THEN A's 502 envelope is returned
- AND B is never attempted

#### Scenario: All candidates failed returns 503

- GIVEN A and B both fail with retryable errors
- WHEN the attempt chain exhausts all candidates
- THEN a sanitized 503 `all_providers_failed` envelope is returned

### Requirement: Per-Attempt Telemetry (planned)

The system MUST record one telemetry hop per attempt with bounded labels — provider, model, outcome (`success`|`error`), and `error.type` from the existing allowed sets. A failed attempt on A followed by success on B MUST emit an error hop for A and a success hop for B. The request counter MUST count attempts, not requests. Hops MAY carry a bounded `fallback_attempts` attribute (integer, <= candidate count).

#### Scenario: Each attempt emits its own hop

- GIVEN A fails retryably and B succeeds
- WHEN the attempt chain runs
- THEN an error hop is recorded for A and a success hop for B
- AND labels stay within the allowed sets

### Requirement: Streaming Requests Skip Fallback (planned)

The system MUST return 501 for `stream=true` before any selection, attempt, or telemetry.

#### Scenario: Streaming request short-circuits

- GIVEN a `stream=true` request and any candidate set
- WHEN the chat handler processes it
- THEN a 501 envelope is returned and no provider is attempted

## Non-Goals (Explicit)

MUST NOT add model alias federation, health-state pre-selection, circuit breakers, same-provider retry/backoff, or per-request fallback controls. Fallback MUST trigger only among providers configured with the exact same model id; disjoint `gpt-*`/`claude-*` ids make it fire only when operators overlap ids — an explicit boundary.

#### Scenario: Disjoint model ids do not fail over

- GIVEN one provider offers `gpt-4` and another only `claude-3`
- WHEN a request for `gpt-4` fails retryably
- THEN the all-failed 503 envelope is returned
