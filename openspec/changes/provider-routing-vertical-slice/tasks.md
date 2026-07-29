# Tasks: Provider Routing Vertical Slice

> Change: `provider-routing-vertical-slice` · Tracker: `feat/provider-routing-vertical-slice` (no-merge) · `auto-chain` / `feature-branch-chain` · 400 authored lines/PR.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Total authored lines | 650–800 (3 PRs) |
| PR #1 / #2 / #3 | 250–300 / 150–200 / 250–300 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

## Phase 1: Config, Errors, Adapter, Registry (PR #1)

`feat/.../pr-1-config-adapter-registry` ← tracker → tracker. Test: `pytest -q tests/test_provider_routing_slice.py -k "settings or errors or adapter or registry"`. Harness: TestClient+`MockTransport`. Rollback: revert `config.py`+`.env.example`; delete `core/errors.py`, `core/providers/{openai,registry}.py`.

- [x] 1.1 RED — settings defaults + missing-key fail-fast fails.
- [x] 1.2 GREEN `config.py`: extend Settings with `OPENAI_*` + fail-fast; update `.env.example`.
- [x] 1.3 RED — `LLMuxError` status + envelope shape fails.
- [x] 1.4 GREEN `core/errors.py`: `LLMuxError` hierarchy + `to_openai_envelope()`.
- [x] 1.5 RED — `OpenAIAdapter` Protocol + `complete_stream` raises fails.
- [x] 1.6 GREEN `core/providers/openai.py::OpenAIAdapter`: injected `AsyncClient`; full Protocol; HTTP/timeout/malformed → `UpstreamError`/`UpstreamTimeoutError`; `complete_stream` → `NotImplementedError`.
- [x] 1.7 RED — registry order/empty/misconfig fails.
- [x] 1.8 GREEN `core/providers/registry.py::build_providers(settings) -> ProviderRegistry`: ordered adapters + `aclose()`; misconfig → `ConfigurationError`; empty → empty.

## Phase 2: Router, Lifespan, /v1/models (PR #2)

`feat/.../pr-2-router-lifespan-models` ← PR #1 → PR #1. Test: `pytest -q tests/test_provider_routing_slice.py -k "router or models"`. Harness: TestClient `/v1/models` populated/empty. Rollback: revert `main.py`, `api/models.py`; delete `core/router.py`.

- [x] 2.1 RED — `select_provider` first-match + no-match fails.
- [x] 2.2 GREEN `core/router.py::select_provider(model, providers)`: serial `await adapter.models()`, first match wins, `ProviderSelectionError` (400) when none.
- [x] 2.3 RED — `/v1/models` populated + empty-registry fails.
- [x] 2.4 GREEN `api/models.py::list_models` async; aggregate from `app.state.providers`; emit `{id, object:"model", created:0, owned_by}` per (provider, model).
- [x] 2.5 RED — lifespan builds + closes registry fails.
- [x] 2.6 GREEN `main.py::create_app` lifespan: `build_tracer` → `build_providers` → yield → `providers.aclose()` in `finally` → `shutdown_tracer`; attach `app.state.providers`.
- [x] 2.7 REFACTOR — invert `tests/test_unit_2.py::test_models_*_empty_data` to empty-registry path.

## Phase 3: Chat, Error Envelopes, Telemetry (PR #3)

`feat/.../pr-3-chat-telemetry` ← PR #2 → PR #2. Test: `pytest -q tests/test_provider_routing_slice.py -k "chat or stream_501 or telemetry"`. Harness: TestClient 200/400/502/504 + `stream=true` 501 no SSE. Rollback: revert `api/chat.py`, `tests/test_unit_2.py`; delete `observability/metrics.py`.

- [x] 3.1 RED — `stream=false` 200 success fails.
- [x] 3.2 GREEN `api/chat.py::post_chat_completion` async: `stream=true`→501; else select+call+reconstruct OpenAI envelope; OTel span `chat.completion`.
- [x] 3.3 RED — upstream 502 + timeout 504 fails.
- [x] 3.4 GREEN — map `ProviderSelectionError`→400, `UpstreamError`→502, `UpstreamTimeoutError`→504, `ConfigurationError`→502.
- [x] 3.5 RED — `stream=true` 501-no-SSE + omitted-`stream` defaults-false fails.
- [x] 3.6 GREEN — invert `tests/test_unit_2.py::test_chat_501_for_all_stream_modes` to `stream=true`-only; add omitted-`stream` test.
- [x] 3.7 RED — span + 3-metrics fails (no instruments).
- [x] 3.8 GREEN `observability/metrics.py`: counters+histogram per spec via `opentelemetry-api`; record every hop.
- [x] 3.9 REFACTOR — extract OpenAI envelope builder; verify zero `data:` frames, zero `text/event-stream`.

Tracker draft/no-merge; rollback 3 → 2 → 1.
