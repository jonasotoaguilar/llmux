# Tasks: Provider Fallback Slice

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~520–620 (PR1 ~230 · PR2 ~330 · PR3 ~140) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Work Units

| Unit | Goal | PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|----|----------------------|-----------------|-------------------|
| 1 | Classifier + selector; first-match preserved | PR 1 | `uv run pytest -q tests/test_provider_routing_slice.py -k "is_retryable or candidates or selection"` | TestClient: unknown model → 400 (doubles) | Revert `errors.py`/`router.py`/`chat.py` |
| 2 | Attempt loop + 503 + fallback matrix | PR 2 | `uv run pytest -q tests/test_provider_routing_slice.py -k "fallback or all_providers_failed or attempt"` | TestClient: A 503 → B 200; exact-once, sanitized | Revert `chat.py` loop → PR 1 path |
| 3 | Telemetry + regressions + gates | PR 3 | `uv run pytest -q --cov=llmux --cov-fail-under=90`; `uv run ruff check . && uv run mypy src tests` | N/A — in-suite OTel exporter; live keys out of scope | N/A — verification-only, empty revert |

Base boundaries (pending): chain ⇒ PR1 base = tracker `feat/provider-fallback-slice`, PR2 base = PR1, PR3 base = PR2; stacked ⇒ `main`.

Threat matrix: all rows N/A (no file/Git/PR boundary); no RED cases.

## Phase 1: Classifier + 503 Error (PR 1)

- [x] 1.1 Add `is_retryable(error)` to `src/llmux/core/errors.py`: timeout/408/429/≥500/no-status ⇒ True; other 4xx/selection/config/unexpected ⇒ False.
- [x] 1.2 Add `AllProvidersFailedError` in `errors.py`: `status_code=503`, `code="all_providers_failed"`, `error_type="api_error"`.
- [x] 1.3 Parametrized classifier tests: timeout/408/429/503/statusless ⇒ retryable; 401/404/selection/config ⇒ not.
- [x] 1.4 Test 503 envelope sanitized (no keys/bodies/stack traces).

## Phase 2: Ordered Selection (PR 1)

- [x] 2.1 Replace `select_provider` with async `select_candidates` in `src/llmux/core/router.py`: all matching adapters in configured order; empty ⇒ `ProviderSelectionError`; delete old fn.
- [x] 2.2 Tests: A-then-B order, non-matching excluded, no-match ⇒ 400.
- [x] 2.3 Route `src/llmux/api/chat.py` via `select_candidates(...)[0]`; keep 501/envelopes/telemetry green.

## Phase 3: Attempt Loop + Envelopes (PR 2)

- [x] 3.1 Rework `post_chat_completion`: attempt candidates exactly once in order; retryable ⇒ next; non-retryable ⇒ envelope; first success ⇒ 200.
- [x] 3.2 Exhaustion ⇒ sanitized 503 `AllProvidersFailedError`; no synthetic hop; unexpected exceptions still 500.
- [x] 3.3 Fallback matrix: 5xx/408/429/timeout/transport fail over; 401 stops (B untried); all-failed ⇒ 503; first success wins; exact-once (no dupes/concurrency/`aclose`); disjoint ids ⇒ 503.

## Phase 4: Telemetry + Regressions (PR 3)

- [x] 4.1 Wrap each `complete` call in its own `ChatCompletionTimer`; one error/success hop per attempt.
- [x] 4.2 Telemetry: error+success hops; `requests_total` counts attempts; bounded labels; no exhaustion hop; miss keeps `none`/`unknown` hop.
- [x] 4.3 Regressions: `stream=true` ⇒ 501 zero telemetry; selection miss ⇒ 400 one hop.

## Phase 5: Quality Gates + Docs (PR 3)

- [x] 5.1 `uv run pytest -q --cov=llmux --cov-fail-under=90` full suite green.
- [x] 5.2 `uv run ruff check . && uv run mypy src tests` clean; refresh `router.py`/`chat.py`/`errors.py` docstrings + error map.
