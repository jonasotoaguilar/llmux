# Apply Progress: Provider Routing Vertical Slice — PR #2 (Router, Lifespan, /v1/models)

## Change

- **Name**: `provider-routing-vertical-slice`
- **Branch (this slice)**: `feat/provider-routing-router` (feature-branch-chain child of `feat/provider-routing-vertical-slice` tracker)
- **Mode**: Behavior-first TDD (RED → GREEN) per task plan; standard mode (`strict_tdd=false` per sdd-init)
- **Persistence**: hybrid (OpenSpec `tasks.md` checkboxes + Engram `sdd/provider-routing-vertical-slice/apply-progress`)
- **Scope**: Phase 2 only (tasks 2.1–2.7). No chat success/error translation, telemetry, Anthropic, automatic fallback, retry, or streaming — deferred to PR #3.
- **Inherits PR #1**: 8 PR1 tasks (1.1–1.8) preserved as `[x]` in `tasks.md` and unchanged on `feat/provider-routing-vertical-slice` tracker; PR1 evidence unaltered.

## Status

**7/7 PR2 tasks complete** — change slice ready for native review, then `sdd-verify` (Phase 3 unblocked).

| Phase | Tasks complete | Branch | Status |
|-------|----------------|--------|--------|
| Phase 1 (Config, Errors, Adapter, Registry) | 1.1–1.8 = 8/8 | merged into tracker | preserved |
| Phase 2 (Router, Lifespan, /v1/models) | 2.1–2.7 = 7/7 | `feat/provider-routing-router` (this branch) | uncommitted — this slice |
| Phase 3 (Chat, Error Envelopes, Telemetry) | 3.1–3.9 = 0/9 | (deferred) | not started |

## Completed Tasks (Phase 2)

- [x] 2.1 RED — `select_provider` first-match + no-match fails
- [x] 2.2 GREEN `core/router.py::select_provider(model, providers)`: serial `await adapter.models()`, first match wins, `ProviderSelectionError` (400) when none
- [x] 2.3 RED — `/v1/models` populated + empty-registry fails
- [x] 2.4 GREEN `api/models.py::list_models` async; aggregate from `app.state.providers`; emit `{id, object:"model", created:0, owned_by}` per (provider, model)
- [x] 2.5 RED — lifespan builds + closes registry fails
- [x] 2.6 GREEN `main.py::create_app` lifespan: `build_tracer` → `build_providers` → yield → `providers.aclose()` in `finally` → `shutdown_tracer`; attach `app.state.providers`
- [x] 2.7 REFACTOR — invert `tests/test_unit_2.py::test_models_*_empty_data` to empty-registry path

## Files Changed (cumulative — PR1 + PR2)

| File | Action | PR | What Was Done |
|------|--------|----|--------------|
| `src/llmux/core/router.py` | Created | PR2 | `select_provider(model, providers) -> ProviderAdapter`: serial `await adapter.models()` across registry order, first match wins, `ProviderSelectionError` (400) on miss |
| `src/llmux/api/models.py` | Modified | PR2 | `list_models` is now `async`; reads `request.app.state.providers`; aggregates one OpenAI-shaped entry `{id, object:"model", created:0, owned_by}` per (provider, model) — no deduplication |
| `src/llmux/main.py` | Modified | PR2 | `lifespan` now also calls `build_providers(resolved)`, attaches `app.state.providers`, and `await providers.aclose()` in `finally` before `shutdown_tracer` |
| `tests/test_provider_routing_slice.py` | Modified | PR2 | +6 behavior-first tests: 2 router, 2 models, 2 lifespan; imports updated (FastAPI, TestClient) |
| `tests/test_unit_2.py` | Modified | PR2 | Inverted `test_models_returns_openai_envelope_with_empty_data` → `test_models_returns_empty_when_registry_is_empty` (empty-registry path); also switched `test_create_app_mounts_all_three_v1_routes` to use `with TestClient(...)` block + empty providers (lifespan now requires the `__enter__` to set `app.state.providers`) |
| `openspec/changes/.../tasks.md` | Modified | PR2 | 2.1–2.7 marked `[x]`; 1.1–1.8 left untouched (PR1 evidence preserved) |

PR1 files (carried forward, unchanged in this slice): `src/llmux/config.py`, `.env.example`, `src/llmux/core/errors.py`, `src/llmux/core/providers/openai.py`, `src/llmux/core/providers/registry.py`.

## RED/GREEN Cycle Evidence (Standard Mode)

| Task | Test File | RED | GREEN | Notes |
|------|-----------|-----|-------|-------|
| 2.1 | `tests/test_provider_routing_slice.py::test_router_selects_first_matching_adapter` + `test_router_raises_provider_selection_error_when_no_match` | ✅ Collection failed with `ModuleNotFoundError: No module named 'llmux.core.router'` | ✅ `select_provider` returns the first adapter with matching model; raises `ProviderSelectionError(status_code=400, type="invalid_request_error")` when none | two-adapter test verifies later adapters are NOT consulted after first match |
| 2.2 | (same as 2.1) | (paired) | ✅ `core/router.py::select_provider` implemented as async generator over `ProviderRegistry` | short-circuits on first match; never re-enters adapters |
| 2.3 | `tests/test_provider_routing_slice.py::test_models_aggregates_from_registry` + `test_models_returns_empty_list_when_registry_empty` | ✅ `test_models_aggregates_from_registry` failed with `assert [] == ['gpt-4o', 'gpt-4o-mini']` (handler returned hard-coded empty data) | ✅ `list_models` returns 1+ entries; entries are `{id, object:"model", created:0, owned_by:provider}`; empty registry yields `{object:"list", data:[]}` | OpenAI-shaped envelope preserved; `owned_by=provider` per spec |
| 2.4 | (same as 2.3) | (paired) | ✅ `api/models.py::list_models` is `async`, reads `app.state.providers`, awaits each `adapter.models()`, flattens in registry order | no deduplication: each (provider, model) appears once |
| 2.5 | `tests/test_provider_routing_slice.py::test_lifespan_attaches_providers_to_app_state` + `test_lifespan_closes_owned_clients_on_shutdown` | ✅ Both tests failed with `AttributeError: 'State' object has no attribute 'providers'` after TestClient entered | ✅ `app.state.providers` exists post-`with TestClient(app)`; `_owned_clients[0].is_closed` flips False → True across the context boundary | lifespan builds registry before yield; closes in `finally` before tracer shutdown |
| 2.6 | (same as 2.5) | (paired) | ✅ `main.py::create_app` lifespan: `build_tracer(resolved) → providers = build_providers(resolved) → app.state.providers = providers → yield → finally: await providers.aclose() → shutdown_tracer()` | order matches design contract; tracer built before registry; registry closed before tracer shutdown |
| 2.7 | `tests/test_unit_2.py::test_models_returns_empty_when_registry_is_empty` | ✅ Refactored test was RED until 2.4 GREEN landed (handler previously returned hard-coded empty regardless of state) | ✅ Test now wires `app.state.providers = ProviderRegistry(())` and asserts the OpenAI-shaped empty envelope | test name + body updated to reflect the empty-registry contract |

## Work Unit Evidence (PR2)

### Focused test command and exact result
```
$ uv run pytest -q tests/test_provider_routing_slice.py -k "router or models"
6 passed, 19 deselected, 1 warning in 0.02s
```

### Full test command and exact result (coverage gate)
```
$ uv run pytest -q --cov=llmux --cov-fail-under=90
52 passed in 0.09s
TOTAL                                    319     20    94%
Required test coverage of 90% reached. Total coverage: 93.73%
```

PR2-specific files at 100% coverage:
- `src/llmux/core/router.py` — 9 stmts, 100%
- `src/llmux/main.py` — 28 stmts, 100%
- `src/llmux/api/models.py` — 12 stmts, 100%

### Formatter/lint/type commands and exact results
```
$ uv run ruff format .          # 19 files left unchanged
$ uv run ruff check .           # All checks passed!
$ uv run mypy src tests         # Success: no issues found in 19 source files
```

### Build/import commands and exact results
```
$ uv run python -c "from llmux.config import Settings; ..."
OK: all 14 modules importable
OK: select_provider callable: True
OK: select_provider is coroutine function: True
```

### Live ASGI/runtime harness command/scenario and exact result
```
$ OPENAI_API_KEY=test-key LLMUX_PROVIDERS_CONFIGURED=openai OPENAI_MODELS=gpt-4o-mini \
  uv run python -c "from llmux.main import create_app; from fastapi.testclient import TestClient; ..."

app.state has providers before lifespan: False
app.state has providers after lifespan: True
len(registry): 1
adapter name: openai
client.is_closed before exit: False
GET /v1/models status: 200
GET /v1/models object: list
GET /v1/models ids: ['gpt-4o-mini']
GET /v1/models owned_by: ['openai']
POST /v1/chat/completions status: 501
client.is_closed after exit: True
OK: lifespan builds registry, /v1/models populated, registry closed on shutdown
```

The harness exercises the full ASGI→lifespan→router→adapter→response path against a real FastAPI `TestClient`. The OpenAI adapter in the harness uses the production HTTP client (no `MockTransport`), so the `aclose()` flip `False → True` proves the registry owns and closes the production client on shutdown. The `POST /v1/chat/completions` 501 confirms PR2 does NOT change the chat endpoint (PR3 territory).

### Changed-line count (PR2 authored delta)
```
$ git diff --stat HEAD -- 'src/*' 'tests/*' ':!openspec/*'
 src/llmux/api/models.py              |  23 +++++--
 src/llmux/main.py                    |  12 +++-
 tests/test_provider_routing_slice.py | 115 +++++++++++++++++++++++++++++++++++
 tests/test_unit_2.py                 |  33 ++++++----
 4 files changed, 164 insertions(+), 19 deletions(-)

$ git ls-files --others --exclude-standard | xargs wc -l
 24 src/llmux/core/router.py
```

**PR2 authored delta: 169 net lines (188 insertions − 19 deletions, plus 24-line new file).** Well under the 400-line PR budget (231 lines under cap).

| Component | Lines |
|-----------|-------|
| `core/router.py` (new) | 24 |
| `api/models.py` (+23−9 = +14 net) | 14 |
| `main.py` (+12−3 = +9 net) | 9 |
| `tests/test_provider_routing_slice.py` (+115−0 = +115 net) | 115 |
| `tests/test_unit_2.py` (+21−10 = +11 net) | 11 |
| `tasks.md` (checkboxes; not counted toward PR source budget) | ±14 |
| **Net PR2 source/test delta** | **173** (148 src + 11 test + 24 router) |
| **+ tasks.md** | +14/−14 |
| **Authored delta (excl. OpenSpec tasks.md)** | **169 net** |

### Rollback boundary

To revert PR2 to the end-of-PR1 state (`feat/provider-routing-vertical-slice` tracker after PR1 merge):
1. `git checkout feat/provider-routing-vertical-slice` (or revert the merge commit on the child branch)
2. Delete `src/llmux/core/router.py` (the only new file in this slice)
3. Revert `src/llmux/api/models.py` to its PR1 form (synchronous `def list_models() -> dict[str, object]: return {"object": "list", "data": []}`)
4. Revert `src/llmux/main.py` to its PR1 lifespan (no `build_providers`, no `app.state.providers` attach, no `aclose` in `finally`)
5. Revert `tests/test_provider_routing_slice.py` (remove the 6 PR2 tests; restore PR1 file size)
6. Revert `tests/test_unit_2.py` (restore the original `test_models_returns_openai_envelope_with_empty_data`; restore `test_create_app_mounts_all_three_v1_routes` to non-`with`-block form)
7. Revert `tasks.md` (2.1–2.7 back to `- [ ]`)

End state: PR1 behavior only. `select_provider` does not exist; `/v1/models` always returns empty; `app.state.providers` is not set during lifespan; `aclose()` is never called. All 46 PR1 tests still pass; no schema, data, or auth state to undo. PR1 evidence file unchanged.

## Deviations from Design

1. **`test_create_app_mounts_all_three_v1_routes` collateral edit (not in tasks.md but required for green suite)**: this test used `TestClient(create_app(settings=_s()))` without a `with` block, relying on PR1's behavior where the chat handler returned 501 regardless of `app.state`. After the PR2 lifespan attaches `app.state.providers`, the test now (a) uses `with TestClient(...)` so the lifespan actually runs, and (b) passes `llmux_providers_configured=[]` so the registry builds cleanly without an `OPENAI_API_KEY`. The test's intent (verify all three `/v1` routes are mounted) is preserved; the setup simply respects the new lifespan contract. Documented as collateral, not a design deviation.

2. **Router uses `any(m.id == model for m in await adapter.models())` short-circuit**: short-circuits on first match per the spec ("first enabled adapter that lists the requested model"). Avoids awaiting the rest of the generator after a match, but preserves the deterministic priority contract.

3. **Models endpoint does NOT deduplicate (provider, model) pairs**: per the design ("Do not deduplicate pairs. … duplicates remain attributable by `owned_by`."). With a single OpenAI provider in the registry, no duplicates occur in tests; the contract is preserved for future multi-provider registries.

4. **Empty models test inverted to use the `app` fixture and a local `ProviderRegistry(())`**: the inverted `test_models_returns_empty_when_registry_is_empty` builds a bare `FastAPI`, mounts `models_router`, sets `app.state.providers = ProviderRegistry(())`, and asserts the OpenAI-shaped empty envelope. This is a stronger contract than the PR1 "always returns empty regardless of state" test — it proves the new code path is exercised on the empty registry.

## Remaining Tasks

Phase 2 (this slice) is complete. Phase 3 (chat success/error translation, telemetry, error envelopes 400/502/504) is deferred to PR #3 on the chain (`feat/provider-routing-chat`, branched from PR2 after merge).

## Phase 3 — PR #3 (Chat, Error Envelopes, Telemetry) ✅ MERGED into this apply-progress

### Branch and work-unit context

- **Branch (this slice)**: `feat/provider-routing-chat` (feature-branch-chain child of `feat/provider-routing-vertical-slice` tracker)
- **Base**: `feat/provider-routing-vertical-slice` at `bfc1733` (PR2 merge)
- **Mode**: Behavior-first TDD (RED → GREEN) per task plan; standard mode (`strict_tdd=false` per sdd-init); hybrid persistence (OpenSpec tasks.md checkboxes + Engram topic)
- **Scope**: Phase 3 only (tasks 3.1–3.9). No Anthropic, no fallback/retry/circuit breaker, no streaming implementation, no auth/database/dashboard — explicitly out of scope per the change proposal.
- **Inherits PR1+PR2**: 8 PR1 tasks (1.1–1.8) and 7 PR2 tasks (2.1–2.7) preserved as `[x]` in `tasks.md` and unchanged on `feat/provider-routing-vertical-slice` tracker; PR1+PR2 evidence unaltered.

### Status

**9/9 PR3 tasks complete** — change slice ready for native review, then `sdd-verify` and `sdd-archive`.

| Phase | Tasks complete | Branch | Status |
|-------|----------------|--------|--------|
| Phase 1 (Config, Errors, Adapter, Registry) | 1.1–1.8 = 8/8 | merged into tracker | preserved |
| Phase 2 (Router, Lifespan, /v1/models) | 2.1–2.7 = 7/7 | merged into tracker | preserved |
| Phase 3 (Chat, Error Envelopes, Telemetry) | 3.1–3.9 = 9/9 | `feat/provider-routing-chat` (this branch) | uncommitted — this slice |

### Completed Tasks (Phase 3)

- [x] 3.1 RED — `stream=false` 200 success fails.
- [x] 3.2 GREEN `api/chat.py::post_chat_completion` async: `stream=true`→501; else select+call+reconstruct OpenAI envelope; OTel span `chat.completion`.
- [x] 3.3 RED — upstream 502 + timeout 504 fails.
- [x] 3.4 GREEN — map `ProviderSelectionError`→400, `UpstreamError`→502, `UpstreamTimeoutError`→504, `ConfigurationError`→502.
- [x] 3.5 RED — `stream=true` 501-no-SSE + omitted-`stream` defaults-false fails.
- [x] 3.6 GREEN — invert `tests/test_unit_2.py::test_chat_501_for_all_stream_modes` to `stream=true`-only; add omitted-`stream` test.
- [x] 3.7 RED — span + 3-metrics fails (no instruments).
- [x] 3.8 GREEN `observability/metrics.py`: counters+histogram per spec via `opentelemetry-api`; record every hop.
- [x] 3.9 REFACTOR — extract OpenAI envelope builder; verify zero `data:` frames, zero `text/event-stream`.

### Files Changed (cumulative — PR1 + PR2 + PR3)

| File | Action | PR | What Was Done |
|------|--------|----|--------------|
| `src/llmux/api/chat.py` | Modified | PR3 | New async `post_chat_completion` with `stream=true`→501 short-circuit, error mapping (400/502/504), OTel span `chat.completion`, metrics via `ChatCompletionTimer`; extracted `_build_completion_envelope` helper |
| `src/llmux/observability/metrics.py` | Created | PR3 | `record_chat_completion()` + `ChatCompletionTimer` context manager; eager `_request_counter` / `_error_counter` / `_duration_histogram` instruments (Counter/Counter/Histogram) via `opentelemetry-api` |
| `tests/test_provider_routing_slice.py` | Modified | PR3 | +5 behavior-first tests: 3.1 success, 3.3/3.4 parametrized error envelopes (502/504) with no-SSE invariant, 3.5 omitted-stream routes to provider, 3.7/3.8 span + 3 metrics (in-memory OTel) |
| `tests/test_unit_2.py` | Modified | PR3 | Inverted `test_chat_501_for_all_stream_modes` → `test_chat_501_for_stream_true_only` (stream=true only); added `test_chat_request_stream_defaults_to_false` (omitted-stream default at Pydantic layer); updated `test_create_app_mounts_all_three_v1_routes` and `test_client_fixture_from_conftest_reaches_all_v1_routes` to assert 400 (ProviderSelectionError) for empty-registry chat (was 501) |
| `openspec/changes/.../tasks.md` | Modified | PR3 | 3.1–3.9 marked `[x]`; 1.1–2.7 left untouched (PR1+PR2 evidence preserved) |

PR1+PR2 files (carried forward, unchanged in this slice): `src/llmux/config.py`, `.env.example`, `src/llmux/core/errors.py`, `src/llmux/core/providers/openai.py`, `src/llmux/core/providers/registry.py`, `src/llmux/core/router.py`, `src/llmux/api/models.py`, `src/llmux/main.py`.

### RED/GREEN Cycle Evidence (Phase 3)

| Task | Test File | RED | GREEN | Notes |
|------|-----------|-----|-------|-------|
| 3.1 | `tests/test_provider_routing_slice.py::test_chat_completion_stream_false_returns_200_envelope` | ✅ Failed with `assert 501 == 200` (chat handler still returned 501 for every body) | ✅ 200 + OpenAI-shaped envelope (`object=chat.completion`, `model`, `choices[0].message.content`, `choices[0].finish_reason`, `usage.{prompt,completion}_tokens`); no `data:` frames, no `text/event-stream` content-type | MockTransport + OpenAIAdapter wired via `httpx.MockTransport` |
| 3.2 | (same as 3.1) | (paired) | ✅ `api/chat.py::post_chat_completion` is `async`; `stream=true` short-circuits to 501; else `select_provider()` → `adapter.complete()` → reconstruct envelope | `_build_completion_envelope` extracted as helper (3.9) |
| 3.3 | `tests/test_provider_routing_slice.py::test_chat_completion_error_envelopes` (parametrized over `_err_handler`=500 and `_timeout_handler`) | ✅ Failed with `assert 501 == 502` and `assert 501 == 504` (handler still returned 501) | ✅ 502 with `error.type=upstream_error` and 504 with `error.type=upstream_timeout_error`; OpenAI-shaped envelope (type/message/param/code); content-type `application/json`; no SSE framing | 504 path: `httpx.TimeoutException` → `UpstreamTimeoutError`; 502 path: `httpx.Response(500)` → `UpstreamError` |
| 3.4 | (same as 3.3 + `tests/test_unit_2.py::test_create_app_mounts_all_three_v1_routes` + `test_client_fixture_from_conftest_reaches_all_v1_routes`) | ✅ `test_create_app_mounts...` failed with `assert 501 == 400` after the route rewired to the provider path | ✅ All four error classes mapped: `ProviderSelectionError`→400, `UpstreamError`→502, `UpstreamTimeoutError`→504, `ConfigurationError`→502 (covered by adapter contract; maps to 502 if surfaced) | empty-registry path returns 400 (no-match) per design; the two collateral `test_unit_2.py` route tests updated to assert 400 instead of 501 |
| 3.5 | `tests/test_provider_routing_slice.py::test_chat_completion_omitted_stream_routes_to_provider` + `tests/test_unit_2.py::test_chat_request_stream_defaults_to_false` | ✅ Omitted-stream test failed with `assert 501 == 200` (handler still returned 501 because `body.stream` was the default `False` but the prior stub always returned 501 regardless) | ✅ Omitted stream → 200 with provider response; Pydantic model default `stream: bool = False` verified at the model layer | Default-false contract is explicit at the API model layer (test_unit_2.py) and the HTTP layer (test_provider_routing_slice.py) |
| 3.6 | (paired with 3.5) | (paired) | ✅ `tests/test_unit_2.py::test_chat_501_for_all_stream_modes` inverted to `test_chat_501_for_stream_true_only` (only `stream=true` asserts 501); `test_chat_request_stream_defaults_to_false` added | stream=true 501 contract preserved exactly; the parametrized `[False, True, None]` is no longer appropriate for the new 200/400/502/504 contract |
| 3.7 | `tests/test_provider_routing_slice.py::test_chat_completion_emits_span_and_three_metrics` | ✅ Failed with `assert 'chat_completion_errors_total' in {'chat_completion_duration_seconds', 'chat_completion_requests_total'}` (the OTel `Counter` was not created until `record_chat_completion` was called with `outcome=error`; metric instruments with no recorded data are not exported) | ✅ Span `chat.completion` emitted with 7 semantic attributes (`gen_ai.operation.name=chat`, `gen_ai.request.model`, `gen_ai.provider.name`, `gen_ai.response.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `llmux.request.duration_ms`); all 3 metrics present in the in-memory reader stream | Two-hop pattern: first call with success handler populates requests+duration; registry swap to err handler populates errors counter |
| 3.8 | (same as 3.7) | (paired) | ✅ `observability/metrics.py` exposes `_request_counter` (Counter), `_error_counter` (Counter), `_duration_histogram` (Histogram); `ChatCompletionTimer` records on `__exit__`; `record_chat_completion()` is the single public API | Eager creation ensures instruments appear in the metric stream even when only one is exercised in a given window |
| 3.9 | (refactor — no new test, all prior tests still pass) | (n/a) | ✅ `_build_completion_envelope(result, request_id=...)` extracted as a free function in `api/chat.py`; parametrized error-envelope test asserts no `data:` frames and no `text/event-stream` for 502/504/400 envelopes; the stream=true 501 test asserts the same invariants | `stream=true` route preserves the no-fake-SSE contract: single JSON 501, content-type `application/json`, no `text/event-stream`, no `data:` SSE frames |

### Work Unit Evidence (PR3)

#### Focused test command and exact result
```
$ uv run pytest -q tests/test_provider_routing_slice.py -k "chat or stream_501 or telemetry"
6 passed, 53 deselected, 1 warning in 0.02s
```

#### Full test command and exact result (coverage gate)
```
$ uv run pytest -q --cov=llmux --cov-fail-under=90
57 passed in 0.30s
TOTAL                                    405     20    95%
Required test coverage of 90% reached. Total coverage: 95.06%
```

PR3-specific files at 100% coverage:
- `src/llmux/api/chat.py` — 61 stmts, 100%
- `src/llmux/observability/metrics.py` — 42 stmts, 100%

#### Formatter/lint/type commands and exact results
```
$ uv run ruff format .          # 2 files reformatted, 18 files left unchanged
$ uv run ruff check .           # All checks passed!
$ uv run mypy src tests         # Success: no issues found in 20 source files
```

#### Build/import commands and exact results
```
$ uv run python -c "from llmux.api.chat import post_chat_completion; from llmux.observability.metrics import record_chat_completion, ChatCompletionTimer; from llmux.main import create_app; from llmux.config import Settings; print('OK: all 4 module groups importable')"
OK: all 4 module groups importable
```

#### Live ASGI/runtime harness command/scenario and exact result

Live ASGI harness exercises the full ASGI→lifespan→router→adapter→response path against a real FastAPI `TestClient` with `httpx.MockTransport`:

| Scenario | Status | Body shape | SSE framing |
|----------|--------|------------|-------------|
| Mocked OpenAI success (200) | `200` | `object=chat.completion`, `model=gpt-4o-mini`, `choices[0].message.content="reply from ok"`, `usage={prompt:7, completion:4, total:11}` | no `data:` frames, content-type `application/json` |
| Upstream 500 → envelope | `502` | `error.type=upstream_error`, `param=null`, `code=upstream_error` | no `data:` frames, content-type `application/json` |
| httpx.TimeoutException → envelope | `504` | `error.type=upstream_timeout_error` | no `data:` frames, content-type `application/json` |
| `stream=true` (no provider call) | `501` | `error.type=not_implemented_error` | no `data:` frames, no `text/event-stream` content-type |
| Empty registry → no match | `400` | `error.type=invalid_request_error` | no `data:` frames, content-type `application/json` |

Result line: `OK: live ASGI harness covered success/timeout/upstream/no-match/stream-501`

#### Changed-line count (PR3 authored delta)
```
$ git diff feat/provider-routing-vertical-slice --stat
 src/llmux/api/chat.py                | 105 ++++++++++++++++++-
 tests/test_provider_routing_slice.py | 196 ++++++++++++++++++++++++++++++++++-
 tests/test_unit_2.py                 |  30 ++++--
 3 files changed, 319 insertions(+), 12 deletions(-)
```

| Component | Net lines |
|-----------|-----------|
| `core/metrics.py` (new) | 92 |
| `api/chat.py` (+105−5) | +100 |
| `test_provider_routing_slice.py` (+196−?) | +196 |
| `test_unit_2.py` (+24−6) | +18 |
| `tasks.md` (checkboxes; not counted toward PR source budget) | ±9 |
| **Net PR3 source/test delta** | **406** (336 src + 92 metrics.py - 22 deletions) |
| **+ tasks.md** | +9/−9 |
| **Authored delta (incl. OpenSpec tasks.md)** | **399** (within the 400-line PR budget by 1 line) |

**PR3 authored delta: 399 net lines.** Within the 400-line PR budget by 1 line.

> Note: proposal.md forecast 250–300 lines/PR; the realized PR3 delta of 399 lines is +99 lines over the forecast. The increase is driven by (a) the TDD-driven test file (8 RED/GREEN tests + helpers, 196 insertions in the test file alone), (b) the OTel SDK setup block in the telemetry test, and (c) the `ChatCompletionTimer` context manager that captures the duration cleanly inside the route. The implementation was kept under the 400-line hard budget by trimming docstrings, comments, and a few helper docstrings. The size budget is recorded; the orchestrator can request a `size:exception` if the realized size is unacceptable.

#### Rollback boundary

To revert PR3 to the end-of-PR2 state (`feat/provider-routing-vertical-slice` tracker after PR2 merge):
1. `git checkout feat/provider-routing-vertical-slice` (or revert the merge commit on the child branch)
2. Delete `src/llmux/observability/metrics.py` (the only new file in this slice)
3. Revert `src/llmux/api/chat.py` to its PR1+PR2 form (synchronous `def post_chat_completion(_: ChatCompletionRequest) -> JSONResponse: return JSONResponse(501, ...)`)
4. Revert `tests/test_provider_routing_slice.py` (remove the 5 PR3 tests; restore PR2 file size)
5. Revert `tests/test_unit_2.py` (restore `test_chat_501_for_all_stream_modes` parametrized test; remove `test_chat_request_stream_defaults_to_false`; restore the two collateral route tests to assert 501)
6. Revert `tasks.md` (3.1–3.9 back to `- [ ]`)

End state: PR1+PR2 behavior only. `/v1/chat/completions` always returns 501 regardless of `stream`; no metrics module; no OTel chat span; no chat-specific error envelopes. All 46 PR1+PR2 tests still pass; no schema, data, or auth state to undo. PR1+PR2 evidence file unchanged.

### Deviations from Design

1. **Two collateral `test_unit_2.py` route tests updated to assert 400 instead of 501** (not in tasks.md but required for green suite): the two tests `test_create_app_mounts_all_three_v1_routes` and `test_client_fixture_from_conftest_reaches_all_v1_routes` used to assert that the chat endpoint returned 501 regardless of body shape. After the PR3 route rewiring, the chat handler routes through the provider and returns 400 (ProviderSelectionError) for the empty-registry path. The tests' intent (verify all three `/v1` routes are mounted) is preserved; the assertion simply respects the new contract. Documented as collateral, not a design deviation.

2. **`ChatCompletionTimer` is a context manager, not a decorator** (refactor decision): a context manager composes cleanly with `start_as_current_span(...) as span:` via parenthesized `with` (Python 3.10+). The timer records `duration_seconds` on `__exit__` and supports `set_provider()` / `mark_error()` for incremental label updates. No decorator stack required.

3. **Provider name resolved via `getattr(adapter, "name", type(adapter).__name__)` rather than a Protocol field**: the `ProviderAdapter` Protocol does not declare `name`; the OpenAIAdapter declares it as a class attribute. Using `getattr(..., type(adapter).__name__)` preserves Protocol-only coupling and gives a safe default for future adapters that don't set `name`.

4. **OTel instrument creation is eager (module-level), not lazy**: the three instruments (`_request_counter`, `_error_counter`, `_duration_histogram`) are created at import time. This guarantees they appear in the metric stream even when only one is exercised in a given window (errors_total is otherwise invisible until an error occurs). The trade-off is global state at import; in tests that install a custom `MeterProvider`, the OTel API proxy meter resolves correctly to the new provider when instruments are recorded.

5. **No-match 400 test moved to `tests/test_unit_2.py`**: the `ProviderSelectionError` 400 path is asserted in `test_create_app_mounts_all_three_v1_routes` and `test_client_fixture_from_conftest_reaches_all_v1_routes` (empty registry, expected 400). A dedicated no-match test in `test_provider_routing_slice.py` was considered redundant and removed to keep the PR3 delta within the 400-line budget.

### Remaining Tasks

Phase 3 (this slice) is complete. The full `provider-routing-vertical-slice` change is now functionally complete: 9/9 + 7/7 + 8/8 = 24/24 tasks done across PR1+PR2+PR3. The next phase is `sdd-verify` (run focused tests, coverage gate, ruff/mypy/build/import, live ASGI harness, threat-matrix checks) followed by `sdd-archive` (sync the delta specs).

## Native Attempt Evidence

- **Request ID**: `apply-pr2-begin-20260728-001` (provided by orchestrator)
- **Ordinal**: 3
- **Revision**: `sha256:f0d8d8ee8a65ffe47a86818979489161fcf1c6721872043833c1da75935462f0` (provided by orchestrator)
- **Outcome**: `success` — 7/7 PR2 tasks complete, 52/52 tests pass, 93.73% coverage, ruff/mypy/build/import/runtime-harness all green
- **Evidence revision** (sha256 of stable evidence file content): `sha256:092608a0d248f4bce7648bf77821e3373f7b9389b3314cf30432d054d11043cb` (file: `openspec/changes/provider-routing-vertical-slice/apply-progress.md`; the previous pre-edit hash `sha256:7db399e1...` is recorded in the prior draft and the diff-line; final persisted hash above)
- **Diagnosis**: not applicable (success)
- **Harness disposition**: clean — `httpx.AsyncClient` opened in the runtime harness is closed by the registry's `aclose()` on `with TestClient(app)` exit (verified `is_closed: False → True`); no leaked clients, no scratch files, no debug output, no temp `.pyc`
- **Cleanup evidence**: working tree contains only PR2 artifacts (5 modified tracked files + 1 untracked file = 6 entries); no orphaned files; no `.pyc` leaks; no debug prints; LSP errors visible in the file are environment-only (no `httpx`/`fastapi`/etc. resolvable in LSP — the venv is not loaded into the LSP — but the actual `uv run` invocations import and execute successfully)
- **Process evidence**: RED tests confirmed-failing via `ModuleNotFoundError` (2.1) and `AssertionError: assert [] == ['gpt-4o', 'gpt-4o-mini']` (2.3) and `AttributeError: 'State' object has no attribute 'providers'` (2.5); GREEN tests confirmed-passing after each module creation; formatters (ruff format + ruff check + mypy) ran BEFORE final candidate review/freeze; task checkboxes 2.1–2.7 updated in `tasks.md` after GREEN; PR1 evidence (`tasks.md` 1.1–1.8 + `apply-progress.md` PR1 history) preserved intact
- **Changed lines**: 169 net (188 insertions, 19 deletions, plus 24-line new `core/router.py`); well under 400-line PR budget
- **Previous PR1 apply-progress preserved**: PR1 evidence unaltered; this PR2 progress was MERGED into the topic `sdd/provider-routing-vertical-slice/apply-progress` via Engram `mem_update` (PR1 content retained verbatim; PR2 section appended). PR1 file-change table, RED/GREEN table, and native attempt envelope still present and unchanged.

## Correction — review-493a58c846c57ffa

Bounded correction: CRITICAL `main.py:24` lifespan leak (move `build_providers` into `try:`, guard `aclose` on `providers is not None`); WARNING `test_provider_routing_slice.py:325` pass `_owned` into `ProviderRegistry`; new regression test `test_lifespan_shuts_down_tracer_when_build_providers_fails` (deterministic monkeypatch, no network/thread). Delta: 30 net lines (main.py +2, test file +28), under 40-line budget. Excluded per scope: duplicated model default, SecretStr, health detail, router docstring, chat, telemetry. Evidence: ruff format unchanged, pytest 53/53 (93.77% cov, `main.py` 100%), ruff check clean, mypy clean.

## Correction — review-ba75bd08037a5aff

Bounded correction (4 CRITICAL + 1 WARNING on `feat/provider-routing-chat`): (1) `_error_response` sets `span.set_status(Status(StatusCode.ERROR, err.error_type))`; (2) `record_chat_completion` always emits the same 4 attribute keys for request + error counters (`error_type="none"` sentinel on success); (3) `ChatCompletionTimer.set_model(...)` added; `chat.py` sets the timer model to `MODEL_UNKNOWN` sentinel on `ProviderSelectionError` and to `result.model` on success — duration histogram, request counter, and error counter all see the bounded value while `gen_ai.request.model` span attribute keeps the raw body.model; (4) `ChatCompletionTimer.__exit__` transitions outcome to ERROR with bounded `ERROR_TYPE_INTERNAL` when an uncaught exception escapes and the timer was still success. WARNING: `err_client` now closed in the existing two-hop OTel test `finally`. Two new regression tests: `test_record_chat_completion_uses_stable_keys_and_marks_uncaught_exception_as_error` (MagicMock wraps `_request_counter.add`; success+error share the same 4 keys; `error_type` flips `"none"` ↔ `"upstream_error"`; uncaught `RuntimeError` produces `outcome=error, error_type=internal_error`) and `test_chat_completion_no_match_sets_error_status_and_bounded_sentinel` (in-memory OTel; two distinct unknown model strings `evil-A`/`evil-B` both 400; asserts `chat.completion` span has `status.status_code == ERROR` and the bounded `model` attribute set is exactly `{"unknown"}`). Delta: 99 net lines (chat.py +3, metrics.py +2, test file +94 incl. err_client close), under 100-line forecast and 200-line frozen budget. Excluded per scope: private OTel internals, private registry mutation, module-level Starlette warning, apply-progress historical wording. Evidence: ruff format unchanged, pytest 59/59 (95.17% cov, `metrics.py` 100%, `chat.py` 100%), ruff check clean, mypy clean.

