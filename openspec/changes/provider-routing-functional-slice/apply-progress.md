# Apply Progress: Provider Routing Functional Slice — PR1 (Config + Errors)

## Change

- **Name**: `provider-routing-functional-slice`
- **Branch (this PR)**: `feat/provider-routing-functional-slice-01-config-errors` (child of tracker `feat/provider-routing-functional-slice`)
- **Mode**: Standard (review-driven development OFF by user decision; no review artifacts)
- **PR1 scope (narrowed by orchestrator 2026-07-30)**: config + `LLMuxError` hierarchy only. OpenAI adapter, `ProviderRegistry`/`build_providers`, async router, lifespan wiring, `/v1/models` aggregation, chat routing, and OTel/metrics land in PR2–PR6 to keep this PR well under the 400-line review budget.

## Status

**4/4 PR1 tasks complete** — ready for the next chained PR. PR2–PR6 remain as future work.

- [x] 1.1 RED: `openai_settings_{valid,empty_key_raises,empty_models_raises,invalid_url_raises}`
- [x] 1.2 GREEN: extend `config.py` (key/base_url/models/timeout_s); update `.env.example`
- [x] 1.3 RED: `errors_envelope_{selection_400,config_502,upstream_502,timeout_504,sanitized}`
- [x] 1.4 GREEN: create `core/errors.py` (`LLMuxError`+4 subclasses+`to_openai_envelope`)

## Files Changed (this PR)

| File | Action | What Was Done |
|------|--------|---------------|
| `src/llmux/core/errors.py` | Created | `LLMuxError` base + `ConfigurationError` (502), `ProviderSelectionError` (400), `UpstreamError` (502), `UpstreamTimeoutError(UpstreamError)` (504); class-level `safe_message` so sensitive constructor args never reach the envelope; `to_openai_envelope(error)` helper |
| `src/llmux/config.py` | Modified | Added `openai_api_key: SecretStr \| None`, `openai_base_url`, `openai_models: list[str]`, `openai_timeout_s: float`; added `_parse_str_list` helper for JSON-or-CSV env parsing; `model_validator(mode="after")` raises `ConfigurationError` when `openai` is enabled with empty key, empty models, or non-http(s) URL |
| `.env.example` | Modified | Added `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODELS`, `OPENAI_TIMEOUT_S` with comments about fail-fast semantics |
| `tests/test_provider_routing_slice.py` | Created | 12 focused tests across 1.1/1.2 (valid + 3 fail-fast cases + default) and 1.3/1.4 (4-way status/code/type parametrize, sanitization sweep, ad-hoc-subclass base-default test) |
| `tests/test_unit_2.py` | Modified (minimal) | `test_settings_providers_accepts_json_and_empty` now also sets `OPENAI_API_KEY` + `OPENAI_MODELS` so the new fail-fast validator doesn't trip the test (the JSON parser assertion remains the focus) |
| `openspec/changes/provider-routing-functional-slice/tasks.md` | Modified | PR1 marked `[x]`; added a scope-narrowing note pointing to this batch's config+errors boundary |
| `openspec/changes/provider-routing-functional-slice/apply-progress.md` | Created | This file |

## Work Unit Evidence

- **Focused**: `uv run pytest tests/test_provider_routing_slice.py -v` → `12 passed, 1 warning in 0.01s`
- **Full + coverage**: `uv run pytest -q --cov=llmux --cov-fail-under=90` → `39 passed`, `Total coverage: 98.36%` (gate ≥ 90% reached)
- **Ruff format**: `uv run ruff format src tests` → `16 files left unchanged`
- **Ruff lint**: `uv run ruff check src tests` → `All checks passed!`
- **Mypy strict**: `uv run mypy src tests` → `Success: no issues found in 16 source files`
- **Runtime harness**: N/A — PR1 introduces no new endpoint or adapter; the 501 stub at `/v1/chat/completions` is unchanged and the existing 27 tests from `main` still pass. The 12 new tests cover the new boundaries via direct constructor calls and `pytest.raises`.
- **Rollback**: drop `src/llmux/core/errors.py`; revert `src/llmux/config.py`, `.env.example`, `tests/test_unit_2.py`, `tests/test_provider_routing_slice.py`, `tasks.md`, this file. The 501-stub baseline from the parent tracking commit is preserved (no `core/providers/{openai,registry}.py`, no `core/router.py`, no `api/chat.py` routing, no `observability/metrics.py`).

## Deviations from Design

1. **`model_validator(mode="after")` raises `ConfigurationError` directly.** Pydantic v2.13 propagates non-`ValueError` exceptions from `model_validator` as-is, so `pytest.raises(ConfigurationError)` works in tests; the spec's "fail-fast `ConfigurationError`" is honored without an extra unwrap step.
2. **Minimal existing test adjustment.** `test_settings_providers_accepts_json_and_empty` in `tests/test_unit_2.py` was already asserting `Settings()` succeeds with `LLMUX_PROVIDERS_CONFIGURED=["openai","anthropic"]`. The new fail-fast validator made it fail (it never set `OPENAI_API_KEY`); the test now also sets `OPENAI_API_KEY` and `OPENAI_MODELS`. Test intent is unchanged.
3. **`UpstreamTimeoutError(UpstreamError)`.** Inherits so a single `except UpstreamError` catches the timeout path; the spec table maps them independently (504 vs 502) and the tests verify both behaviors.

## Remaining Tasks (next PRs)

- [ ] 3.1–3.3 — `ProviderRegistry` + `build_providers` with the fail-fast / `aclose` ownership contract.
- [ ] 4.1–4.6 — Async first-match `select_provider`, fail-safe lifespan, `/v1/models` aggregation.
- [ ] 5.1–5.5 — Chat routing + envelopes (no telemetry).
- [ ] 6.1–6.6 — OTel span, three bounded metrics, `MODEL_UNKNOWN` sentinel, uncaught-exception accounting.

---

# PR2 — OpenAI Adapter (base PR1) ✅

**Branch**: `feat/provider-routing-functional-slice-02-openai` (base = PR1 merge `23d299c`). **Scope**: OpenAI non-streaming `ProviderAdapter` only — no registry, no router, no lifespan, no endpoints, no telemetry.

- [x] 2.1 RED: `complete_returns_result`, `complete_stream_raises_not_implemented`
- [x] 2.2 RED: `upstream_4xx_5xx→upstream_error`, `timeout→upstream_timeout`
- [x] 2.3 GREEN: create `core/providers/openai.py` (Protocol, injected `httpx.AsyncClient`)

**Files (this PR)**:
- `src/llmux/core/providers/openai.py` (created): `OpenAIAdapter` (kw-only ctor); `complete` POSTs `/chat/completions` (Bearer, `stream:false`, options merged, `timeout=`); `complete_stream` raises `NotImplementedError`; `models` per id; `health` probes `GET /models`; `_parse_completion` → `CompletionResult`, sanitized `UpstreamError` on any malformed shape.
- `tests/test_provider_routing_slice.py` (extended): +8 behavior-first tests via `httpx.MockTransport` and caller-owned client (`aclose` in test only): protocol; success; request shape; `NotImplementedError`; 8-case parametrized failure map; `models`; 3-case parametrized `health`.
- `tasks.md` + `apply-progress.md` (modified): PR2 marked `[x]`; this evidence appended.

**Work Unit Evidence**:
- **Focused**: `uv run pytest tests/test_provider_routing_slice.py -q` → `28 passed` (`25 passed, 7 deselected` under `-k openai`).
- **Full + coverage**: `uv run pytest -q --cov=llmux --cov-fail-under=90` → `58 passed`; total `98.33%`; `openai.py` = `98%` (56/57 stmts — line 117 is the defensive non-dict guard).
- **Ruff + Mypy**: `uv run ruff format … && uv run ruff check …` → `All checks passed!`; `uv run mypy src tests` → `Success: no issues found in 17 source files`.
- **Import**: `python -c "from llmux.core.providers.openai import OpenAIAdapter; from llmux.core.providers.base import ProviderAdapter, CompletionResult, HealthStatus, ModelInfo; assert isinstance(OpenAIAdapter.__new__(OpenAIAdapter), ProviderAdapter)"` → `OK`.
- **Live MockTransport harness**: real `httpx.AsyncClient(transport=httpx.MockTransport(handler))`, three async calls (`complete`+`models`+`health`) on one caller-owned client inside `async with`, 0 network bytes, 0 client leaks → `LIVE HARNESS OK`.
- **Rollback / no test-client double-close**: drop `openai.py`; revert the test additions. PR1 baseline untouched; no new dep, no env var, no FastAPI route. Every PR2 test calls `await client.aclose()` exactly once in `finally`; the adapter never closes the injected client — verified by the live harness and by the Protocol (no `aclose` exposed).

---

# PR3 — ProviderRegistry + transaction-like build_providers (base PR2) ✅

**Branch**: `feat/provider-routing-functional-slice-03-registry` (base = PR2 merge `df7c155`, child of tracker). **Scope**: ordered `ProviderRegistry` with `RegistryEntry(adapter, client)` ownership signaling; idempotent `aclose()` that closes only factory-owned clients; async `build_providers(settings, *, client_factory=...)` with duplicate / unknown / missing-key validation and `except BaseException` cleanup that closes every client already created before re-raising. No router, no lifespan, no endpoints, no telemetry.

- [x] 3.1 RED: `build_providers_closes_first_client_on_later_failure` (deterministic factory seam), `registry_fail_fast_aborts_on_duplicate_slug`, `build_providers_cleans_up_on_adapter_ctor_failure` (BaseException path), `build_providers_empty_config_returns_empty_registry`
- [x] 3.2 RED: `aclose_closes_production_only` (mixed owned+caller-supplied entries), `aclose_idempotent_after_success` (5× aclose, count==1), `registry_models_aggregates_across_providers`
- [x] 3.3 GREEN: create `core/providers/registry.py` (`ProviderRegistry` + `RegistryEntry` + `build_providers` w/ cleanup seam + `ClientFactory` seam + default factory)

**Files (this PR)**:
- `src/llmux/core/providers/registry.py` (created, 131 LoC).
- `tests/test_provider_routing_slice.py` (extended, +8 behavior tests): `_CountingClient` (per-instance `aclose_count`); `_counting_factory`; `_settings(monkeypatch, providers=...)` helper.
- `openspec/changes/.../tasks.md` (modified): PR3 marked `[x]`.

**Work Unit Evidence**:
- **Focused**: `uv run pytest tests/test_provider_routing_slice.py -k "registry or build_providers or aclose" -v` → `8 passed`.
- **Full + coverage**: `uv run pytest -q --cov=llmux --cov-fail-under=90` → `63 passed`; total `98.66%`; **`registry.py` = 100% (58/58 stmts, 0 missed)**.
- **Ruff + Mypy**: `uv run ruff format src tests && uv run ruff check src tests` → `All checks passed!`; `uv run mypy src tests` → `Success: no issues found in 18 source files` (strict).
- **Import harness**: `uv run python -c "from llmux.core.providers.registry import ProviderRegistry, RegistryEntry, build_providers, ClientFactory; ..."` + signature assertions → `IMPORT HARNESS OK`.
- **Runtime cleanup harness**: real `Settings(LLMUX_PROVIDERS_CONFIGURED='openai', OPENAI_API_KEY='sk-harness', OPENAI_MODELS='gpt-4o-mini')` → `await build_providers(s)` (default factory creates real `httpx.AsyncClient`) → assert `not is_closed` → `aclose()` → assert `is_closed` → 2× more `aclose()` (idempotent) → `RUNTIME CLEANUP HARNESS OK`.
- **No double-close**: `_CountingClient.aclose_count == 1` asserted on every test that exercises cleanup OR aclose (cleanup path AND registry path); mixed-ownership test asserts `mock_client.is_closed is False` after aclose — caller-owned clients are never re-closed.
  - **Deterministic factory seam**: `test_build_providers_closes_first_client_on_later_failure` — `["openai","anthropic"]` + `_counting_factory` → 1 factory call, 2nd slug unknown, 1st client `is_closed and aclose_count == 1`, no registry returned.
  - **Rollback**: drop `registry.py`; revert test additions; revert `tasks.md` and this section. PR1+PR2 baseline untouched; no router, no lifespan, no endpoint, no telemetry, no new env var or dep.

---

# PR4 — Router + Lifespan + /v1/models (base PR3) ✅

**Branch**: `feat/provider-routing-functional-slice-04-router-lifespan-models` (base = PR3 merge `ec08419`, child of tracker). **Scope**: async first-match `select_provider`; fail-safe FastAPI lifespan (build_tracer → build_providers inside try, registry `aclose()` BEFORE tracer shutdown, tracer always shuts down even on build failure, no double-close); `/v1/models` aggregates one OpenAI entry per `(provider, model)` from `app.state.providers`, empty when no providers. No chat routing, no telemetry, no `/v1/chat/completions` change.

- [x] 4.1 RED: `router_first_match_returns_priority_provider`, `router_no_match_raises_provider_selection_error`
- [x] 4.2 GREEN: create `core/router.py` (async first-match `select_provider`, no fallback)
- [x] 4.3 RED: `lifespan_tracer_shutdown_on_build_failure`, `lifespan_aclose_before_tracer_shutdown`
- [x] 4.4 GREEN: modify `main.py` lifespan (try/finally; aclose before shutdown_tracer; tracer always shutdown)
- [x] 4.5 RED: `models_aggregates_one_per_provider_model`, `models_empty_when_no_providers`
- [x] 4.6 GREEN: modify `api/models.py` to source from `app.state.providers`

**Files (this PR)**:
- `src/llmux/core/router.py` (created, 38 LoC): `async def select_provider(model, registry)` walks `registry.providers` in order, returns the first adapter whose `await adapter.models()` contains the requested id; raises `ProviderSelectionError` (HTTP 400) on no match. The error body uses the class-level `safe_message` (no raw model id leak) per the existing envelope contract.
- `src/llmux/main.py` (modified): lifespan now `build_tracer` first, then `await build_providers` inside a `try: ... finally:` so `aclose` (only when a registry was returned) runs BEFORE `shutdown_tracer`. When `build_providers` raises, no `aclose` is attempted (the factory's `except BaseException` already cleaned up partial clients — PR3 invariant), but `shutdown_tracer` always runs. `app.state.providers` is set right before `yield` for handler access.
- `src/llmux/api/models.py` (modified): async handler sources `app.state.providers`; `getattr(..., None)` for the no-lifespan test-harness case returns `{"object":"list","data":[]}`; otherwise `await registry.models()` and shape each `ModelInfo` as `{id, object:"model", created:0, owned_by:provider}`.
- `tests/test_provider_routing_slice.py` (extended, +204 LoC, 6 new tests + helpers): `_make_static_adapter` (Protocol-shaped, caller-owned MockTransport); `_Recorder`; `_patch_lifespan` (patches `build_tracer`/`shutdown_tracer` in BOTH `observability.tracing` and `main` because `create_app` imports the names into its local scope).

**Work Unit Evidence**:
- **Focused**: `uv run pytest tests/test_provider_routing_slice.py -k "router or lifespan or models_" -v` → `6 passed`.
- **Full + coverage**: `uv run pytest -q --cov=llmux --cov-fail-under=90` → `69 passed`; total `98.45%` (gate ≥ 90% reached). `router.py` = 100% (10/10 stmts), `main.py` = 100% (30/30 stmts), `api/models.py` = 100% (13/13 stmts).
- **Ruff + Mypy**: `uv run ruff format src tests && uv run ruff check src tests` → `All checks passed!`; `uv run mypy src tests` → `Success: no issues found in 19 source files` (strict).
- **Import + shape harness**: `python -c "..."` with `inspect.iscoroutinefunction` checks for `select_provider`/`build_providers`/`list_models`/`aclose`/`models`; `inspect.getsource(create_app)` confirms `await registry.aclose()` appears before `shutdown_tracer()`; `inspect.signature(select_provider)` is `(model, registry)`. → `IMPORT + SHAPE HARNESS OK`.
- **Live ASGI runtime harness**: real `httpx.AsyncClient` (production-shaped) registered through the real `ProviderRegistry`; `app.state.providers` populated by the lifespan; `GET /v1/models` via `TestClient` returns `{"object":"list","data":[{"id":"gpt-4o-mini","object":"model","created":0,"owned_by":"openai"}, {"id":"gpt-4o",...}]}`; after `__exit__` the real client `is_closed` is `True` (proves `aclose` ran); the real client is never double-closed. → `LIVE ASGI HARNESS OK`.
- **Startup-failure harness**: patched `build_providers` to raise `ConfigurationError`; `events == ["build_tracer", "build_providers", "shutdown_tracer"]` (no `"aclose"`); tracer still shuts down. → `STARTUP-FAILURE HARNESS OK`.
- **No double-close**: factory-owned clients are created and owned exactly once (`aclose` recorded exactly once on the recording registry in the success path; factory's `BaseException` cleanup owns partial clients in the failure path so the lifespan never re-closes them).
- **PR4 native lines** (this branch vs. parent): `tasks.md` 12, `api/models.py` 41, `main.py` 38, `tests/test_provider_routing_slice.py` 204 added, `core/router.py` 38 new = **333** total (under 400).
- **Rollback**: drop `core/router.py`; revert `main.py` and `api/models.py`; revert the PR4 test additions; revert `tasks.md` and this section. PR3 baseline (config + errors + OpenAI adapter + registry) is fully preserved — the `aclose`-before-`shutdown_tracer` order is reintroduced alongside this PR's changes and is the only order that satisfies the PR3 ownership contract.

---

# PR5 — Chat Routing + Envelopes, no telemetry (base PR4) ✅

**Branch**: `feat/provider-routing-functional-slice-05-chat-routing-envelopes` (base = PR4 merge `a12c526`, child of tracker). **Scope**: async `POST /v1/chat/completions` routes non-streaming requests through the configured router to the selected provider's `complete()`; returns 200 OpenAI-shaped envelope on success, sanitized `LLMuxError` envelope on typed failure (400 `model_not_found`, 502 `upstream_error` / `provider_configuration_error`, 504 `upstream_timeout`). Explicit `stream=true` short-circuits to a JSON 501 *before* any provider call or telemetry work (no-fake-SSE contract). **No telemetry** in this PR — the bounded OTel span, the three metrics, and the `MODEL_UNKNOWN` sentinel land in PR6.

- [x] 5.1 RED: `stream_false_routes_200`, `omitted_stream_defaults_false_routes`
- [x] 5.2 RED: `stream_true_501_no_provider_no_telemetry` (no `data:` frames)
- [x] 5.3 GREEN: short-circuit explicit `stream=True` → JSON 501 (before provider/telemetry)
- [x] 5.4 RED: `chat_{400_selection_miss,502_upstream,504_timeout,502_sanitized}`
- [x] 5.5 GREEN: modify `api/chat.py` to route when `stream is False` (incl. omitted)

**Files (this PR)**:
- `src/llmux/api/chat.py` (modified, 38 → 118 LoC; +84/-4): async handler; `Request` injection; `body.stream is True` short-circuits to 501; otherwise `getattr(request.app.state, "providers", None)` (None → 502 `ConfigurationError` to honor the "502 not 400" rule for startup faults) → `await select_provider(...)` → `await adapter.complete(model, [m.model_dump(exclude_none=True) for m in body.messages])`; `except LLMuxError` → sanitized envelope via `to_openai_envelope`; success → 200 envelope via `_completion_envelope(result)`. Two tiny helpers: `_completion_envelope` (passes through `result.raw` and `setdefault`s `object="chat.completion"` + `created=0`) and `_error_response` (typed error → `JSONResponse` with `error.status_code` + `application/json`).
- `tests/test_provider_routing_slice.py` (extended, +221 LoC, 6 new tests + 2 helpers): reuses the PR2 `_make_adapter` and the PR4 `_patch_lifespan`; new helpers are only `_app_with_registry` (settings + patch + `create_app`) and `_post_chat` (minimal body builder); the 6 tests cover 200, omitted-stream, 501, 400, 502, 504 paths.
- `tests/test_unit_2.py` (modified, +75/-17): the pre-existing `test_chat_501_for_all_stream_modes[false|omitted]` asserted the 501-stub baseline that the proposal explicitly retired — replaced by `test_chat_501_only_for_explicit_stream_true` (single 501 case) and `test_chat_502_when_no_registry_for_non_streaming` (proves non-streaming routes and surfaces a 502 when no `app.state.providers` is set, matching the spec's "502 never 400" rule for `ConfigurationError`); `test_create_app_mounts_all_three_v1_routes` and `test_client_fixture_from_conftest_reaches_all_v1_routes` updated to expect routed 502 (no-API-key `build_providers` raises `ConfigurationError` → `app.state.providers is None`) and explicit-stream 501.
- `openspec/changes/.../tasks.md` (modified): PR5 marked `[x]`.
- `openspec/changes/.../apply-progress.md` (modified): this section.

**Work Unit Evidence**:
- **Focused**: `uv run pytest tests/test_provider_routing_slice.py -k "stream_false_routes or omitted_stream or stream_true_returns or chat_400 or chat_502 or chat_504" -v` → `6 passed` (initial RED had 6 fail / 1 pass — the one pre-passing was `stream_true_returns_501_no_provider_no_telemetry` because the previous 501 stub already returned 501 for every body, so the new test enforces the same contract plus the no-`data:` / JSON-only / call-count-zero guards).
- **Full + coverage**: `uv run pytest -q --cov=llmux --cov-fail-under=90` → `74 passed` (PR4 had 69, so PR5 added 6 net new tests after collapsing the retired 3-way parametrize into 2 focused tests); total `98.55%`; **`api/chat.py` = 100% (42/42 stmts, 0 missed)**.
- **Ruff + Mypy**: `uv run ruff format src tests && uv run ruff check src tests` → `All checks passed!`; `uv run mypy src tests` → `Success: no issues found in 19 source files` (strict).
- **Import + shape harness**: `inspect.iscoroutinefunction(post_chat_completion) == True`; `inspect.signature(post_chat_completion)` is `(request, body)`; `inspect.getsource(post_chat_completion)` contains the short-circuit (`is True`), the router call (`select_provider`), the provider call (`adapter.complete`), the typed-error catch (`LLMuxError`), and the response shape (`JSONResponse`). → `IMPORT + SHAPE HARNESS OK`.
- **Live ASGI runtime harness**: real `create_app` with the lifespan patched to return a real `ProviderRegistry((RegistryEntry(OpenAIAdapter(MockTransport(handler), ...), None),))`; `TestClient` POSTs through the full FastAPI stack:
  - 200 routed: `POST /v1/chat/completions` with `stream: false` → `200`, body has `object: "chat.completion"`, `id: "chatcmpl-harness"`, `choices[0].message.content == "live"`, `Content-Type: application/json` (no `text/event-stream`). → `200 ROUTED OK`.
  - 501 short-circuit: same client, `stream: true` → `501`, `Content-Type: application/json`, no `data:` in body, error code `not_implemented`. → `501 SHORT-CIRCUIT OK`.
  - 502 sanitized: a fresh `MockTransport` whose handler returns `500, text="LEAKED sk-DO-NOT-LEAK internal stack Traceback"` → `502` `upstream_error`; serialized body contains none of `LEAKED`, `sk-DO-NOT-LEAK`, `internal stack`, `Traceback`. → `502 SANITIZED OK`.
  - 504 timeout: handler `raise httpx.TimeoutException("slow", request=r)` → `504` `upstream_timeout`. → `504 TIMEOUT OK`.
  - 400 selection miss: registry offers `gpt-4o-mini` only; request `model: "not-offered"` → `400` `model_not_found`; serialized body does NOT contain `not-offered`. → `400 SELECTION OK`.
  → `LIVE ASGI HARNESS OK` for all five branches.
- **No double-close / no provider leak in 501 path**: the `stream=true` branch returns the 501 JSONResponse BEFORE any registry/adapter touch; the MockTransport handler's `call_count` stays at 0. The 200 branch re-uses the caller-owned client (entry `client=None`); each test owns the lifetime in its `finally` (PR3 aclose-ownership contract preserved).
- **Native lines** (this branch vs. parent, `git diff --numstat`): `src/llmux/api/chat.py` 84/-4, `tests/test_provider_routing_slice.py` 221/0, `tests/test_unit_2.py` 75/-17 = **380** total (under 400).
- **Deviations from design**: None on the routed path; one pragmatic addition: when `app.state.providers is None` (lifespan never ran — the test-harness case), the handler maps to `ConfigurationError` → 502 (never 400) per the spec's "ConfigurationError MUST normalize to 502, never 400" rule. The bare-bones test `test_chat_502_when_no_registry_for_non_streaming` covers this. The pre-existing `from llmux.core.errors import ConfigurationError` is hoisted to a function-local import to keep the import set lean at module level.
- **No telemetry in this PR**: no span, no meter, no `MODEL_UNKNOWN` constant — verified by `git diff` (no `observability/metrics.py` exists on this branch, the handler does not import any `observability` module, the live harness `events` recorder stays empty because `_patch_lifespan` is only used for test injection and PR5 does not read or emit telemetry).
- **Rollback**: revert `src/llmux/api/chat.py` to the 501 stub baseline (38 LoC); revert the 6 added tests + 2 helpers in `tests/test_provider_routing_slice.py`; revert the 2 retitled + 2 retargeted tests in `tests/test_unit_2.py` to the 3-way-parametrized 501-only baseline. PR4 baseline (config + errors + OpenAI adapter + registry + router + lifespan + `/v1/models`) is fully preserved — no changes to `core/router.py`, `core/providers/`, `main.py`, or `api/models.py`.

---

# PR6 — OTel + Metrics + Cardinality + Error Accounting (base PR5) ✅

**Branch**: `feat/provider-routing-functional-slice-06-telemetry-error-accounting` (child of tracker `feat/provider-routing-functional-slice` @ `f98bf96` = post-PR5 merge). **Scope**: one bounded `chat.completion` OTel span + three bounded-cardinality metrics (`chat_completion_requests_total`, `chat_completion_errors_total`, `chat_completion_duration_seconds`) per non-streaming hop. Selection misses use the `MODEL_UNKNOWN` sentinel; unexpected (non-`LLMuxError`) exceptions are recorded as `error.type=internal_error` and re-raised so FastAPI returns a 500. Explicit `stream=true` remains a 501 short-circuit *before* any telemetry work. Telemetry owner accepts a public `Tracer` + `Meter` so tests inject in-memory fakes via `InMemorySpanExporter` / `InMemoryMetricReader` — no private OTel global mutation.

- [x] 6.1 RED: `test_telemetry_model_unknown_sentinel_on_unselected`, `test_telemetry_bounded_label_values`
- [x] 6.2 RED: `test_telemetry_span_error_status_with_error_type_attribute`
- [x] 6.3 GREEN: create `observability/metrics.py` (span `chat.completion`, 3 metrics, `MODEL_UNKNOWN`, `INTERNAL_ERROR_TYPE`, `PROVIDER_NONE` sentinels)
- [x] 6.4 GREEN: wire `ChatTelemetry` into `api/chat.py` routed call site (set_provider, set_model, set_error_type, mark_error)
- [x] 6.5 RED: `test_telemetry_unexpected_error_records_error_metric_and_propagates`
- [x] 6.6 GREEN: re-raise non-`LLMuxError` after error telemetry; mypy strict; update `tasks.md` checklist

**Files (this PR)**:
- `src/llmux/observability/metrics.py` (created, 364 LoC, ~110 LoC logic + docstrings): public `MODEL_UNKNOWN`/`PROVIDER_NONE`/`INTERNAL_ERROR_TYPE`/`ERROR_TYPE_NONE`/`OUTCOME_*`/`METRIC_*`/`ATTR_*` constants; `ALLOWED_OUTCOMES` / `ALLOWED_ERROR_TYPES` bounded sets; `ChatTelemetry(tracer, meter)` (3 instruments, public OTel DI); `ChatCompletionTimer` context manager (`__enter__` opens the span with `record_exception=False, set_status_on_exception=False` so the SDK does not override the bounded status; `set_provider`/`set_model`/`set_error_type`/`mark_error` mutators; `__exit__` records request/error counters and duration, sets `Status(StatusCode.ERROR, error_type)` only on the error path, never swallows); `NoopChatTelemetry` + `_NoopTimer` for the bare-bones test harness (drop-in API parity); `build_chat_telemetry(tracer, meter)` factory.
- `src/llmux/api/chat.py` (modified, 118 → 179 LoC; +86/-25 net): wraps the routed call site in `with telemetry.start(provider=None, model=MODEL_UNKNOWN) as timer`. Explicit `stream=true` short-circuit remains the FIRST statement (before telemetry opens). `telemetry` is read from `app.state.telemetry` with a `_NOOP_TELEMETRY` fallback for the bare-bones harness. After successful selection: `timer.set_provider(getattr(adapter, "name", PROVIDER_NONE))` and `timer.set_model(body.model)` (so an unexpected error after selection still records the request model on the error metric). On any `LLMuxError` the handler calls `timer.set_error_type(type(exc).error_type)` + `timer.mark_error()` so the span status is `Status(ERROR, error_type)` even when the LLMuxError is caught by the handler and translated to a sanitized HTTP envelope. On success: `timer.set_model(result.model)` so the metric carries the canonical result model (not the request model).
- `src/llmux/main.py` (modified, 68 → 87 LoC; +20/-1 net): lifespan now also builds the chat telemetry (`otel_metrics.get_meter("llmux")` + `build_chat_telemetry(tracer, meter)`) and stores it on `app.state.telemetry` BEFORE the `try/finally` so a `ConfigurationError` from `build_providers` does not leave the app in a half-initialised state. The tracer shutdown and registry aclose order from PR4 is preserved.
- `src/llmux/core/providers/base.py` (modified, +10/-1): `ProviderAdapter` Protocol docstring now states the `name` attribute is concrete-class-only (NOT a Protocol member) because `runtime_checkable` Protocols with non-method members break `issubclass`. The chat handler reads the name via `getattr(adapter, "name", PROVIDER_NONE)` so the bounded `provider` label is enforced even when the attribute is missing.
- `tests/test_provider_routing_slice.py` (extended, 1031 → 1525 LoC; +497/-3 net): 6 new tests + 3 helpers (`_make_chat_telemetry`, `_chat_spans`, `_metric_data_points`, `_span_attrs`) + `_RaisingAdapter` (Protocol-shaped test stub that raises `RuntimeError` from `complete()` to prove the uncaught-error path) + `_MetricPoint` TypedDict for stable mypy-strict typing.
- `openspec/changes/.../tasks.md` (modified, +6/-6): PR6 marked `[x]`.
- `openspec/changes/.../apply-progress.md` (modified): this section.

**Bounded contract enforced**:
- `model` label ∈ {`"unknown"` (selection miss only), configured model, `result.model` (success)}.
- `provider` label ∈ {`"openai"`, `"none"`}; the `getattr(adapter, "name", PROVIDER_NONE)` fallback guarantees the bounded set even for Protocol stubs without `name`.
- `outcome` label ∈ {`"success"`, `"error"`}.
- `error.type` label ∈ {`"api_error"`, `"invalid_request_error"`, `"internal_error"` (unexpected), `"none"` (success)}.
- Span status is `UNSET` on success, `Status(StatusCode.ERROR, error_type)` on any error (the status description is the bounded label, NEVER the exception message or upstream payload).
- The SDK's automatic exception recording is DISABLED on the span (`record_exception=False, set_status_on_exception=False`) so the bounded contract holds even when an unexpected exception escapes the `with` block.

**Work Unit Evidence**:
- **Focused** (6 new tests, all pass):
  - `uv run pytest tests/test_provider_routing_slice.py -k "model_unknown_sentinel_on_unselected or bounded_label_values or span_error_status_with_error_type_attribute or unexpected_error_records_error_metric_and_propagates or chat_span_and_three_metrics_on_success or stream_true_still_bypasses_all_telemetry" -v` → `6 passed`.
  - The selection-miss test (`test_telemetry_model_unknown_sentinel_on_unselected`) builds a registry offering only `gpt-4o-mini`, requests `not-offered-LEAK-sentinel-cardinality-12345`, and asserts that the raw model id appears in NO metric label position (the sentinel `unknown` replaces it on all three instruments).
- **Full + coverage**: `uv run pytest -q --cov=llmux --cov-fail-under=90` → `80 passed`; total `97.94%`; `observability/metrics.py` = `96%` (5 lines untested: the `internal_error` fallback when `_error_type` was already set by the handler — covered indirectly by the noop path) ; `api/chat.py` = `100%`; `main.py` = `100%`.
- **Ruff + Mypy**: `uv run ruff format src tests && uv run ruff check src tests` → `20 files left unchanged`, `All checks passed!`; `uv run mypy src tests` → `Success: no issues found in 20 source files` (strict).
- **Import + shape harness**: `python -c "from llmux.observability.metrics import ChatTelemetry, ChatCompletionTimer, NoopChatTelemetry, build_chat_telemetry, SPAN_NAME, METRIC_REQUESTS_TOTAL, METRIC_ERRORS_TOTAL, METRIC_DURATION_SECONDS, ATTR_PROVIDER, ATTR_MODEL, ATTR_OUTCOME, ATTR_ERROR_TYPE, MODEL_UNKNOWN, PROVIDER_NONE, OUTCOME_SUCCESS, OUTCOME_ERROR, ERROR_TYPE_NONE, INTERNAL_ERROR_TYPE, ALLOWED_OUTCOMES, ALLOWED_ERROR_TYPES; ..."` → public constants + bounded sets exposed; `SPAN_NAME == "chat.completion"`; `MODEL_UNKNOWN == "unknown"`; `ALLOWED_OUTCOMES == {"success", "error"}`; `ALLOWED_ERROR_TYPES == {"api_error", "internal_error", "invalid_request_error", "none"}`; all imports succeed with no private OTel / registry mutation. → `IMPORT + SHAPE HARNESS OK`.
- **Live telemetry harness**: real OTel SDK `TracerProvider` + `MeterProvider` with `InMemorySpanExporter` + `InMemoryMetricReader` (public API only), wired into a real `ChatTelemetry` and the full chat handler via `TestClient(create_app(...))`:
  - Success: `POST /v1/chat/completions {model: "gpt-4o-mini"}` → `200`, response body has `model: "gpt-4o-2024-05-13-canonical"` (the OpenAI-side canonical name). Metric `chat_completion_requests_total` carries `{provider: "openai", model: "gpt-4o-2024-05-13-canonical"}` (the **result** model, not the request model). `chat_completion_duration_seconds` carries the same labels. `chat_completion_errors_total` has NO data point on the success branch.
  - Selection miss: `POST {model: "not-offered"}` → `400 model_not_found`; metrics carry `{provider: "none", model: "unknown", outcome: "error", error.type: "invalid_request_error"}` — the raw `not-offered` is never seen on a label position.
  - Explicit `stream=true`: 501 short-circuit, no span, no metric data point for the rejected path. The 501 path is verified by the MockTransport handler `call_count == 0` plus `_metric_data_points` returning `[]` for all three instruments.
  - Caller-owned client (`RegistryEntry(adapter, None)`) is NOT closed by the registry after `aclose()` (the `is_closed` flag stays `False`) — the PR3 ownership contract is preserved end-to-end. → `LIVE TELEMETRY HARNESS OK`.
- **No double-close**: the lifespan's telemetry is built with the global meter/tracer (public `otel_metrics.get_meter("llmux")` / `trace.get_tracer("llmux")`); the test harness overrides `app.state.telemetry` AFTER `TestClient.__enter__` so the lifespan-set noop version is replaced with the in-memory fakes; the `MockTransport`-backed client stays caller-owned (no `aclose` from the registry). Verified by the live harness `client.is_closed == False` after the request.
- **No private OTel/registry mutation**: the new tests use only the public OTel SDK (`TracerProvider`, `MeterProvider`, `InMemorySpanExporter`, `InMemoryMetricReader`, `SimpleSpanProcessor`) and the public `trace.set_tracer_provider` / `metrics.set_meter_provider`. The pre-existing `_reset_otel` private-mutation helper in `tests/test_unit_2.py` is left untouched (out of scope for PR6 — that file's tests do not exercise the chat telemetry path).
- **Deterministic test seams**: the new `ChatCompletionTimer` is constructed with the public `Tracer` and `Meter` (constructor-injected). Tests build their own providers, attach `InMemorySpanExporter` + `SimpleSpanProcessor` and `InMemoryMetricReader`, and pass the resulting tracer/meter to `ChatTelemetry`. The lifespan's noop telemetry is overridden by `app.state.telemetry = telemetry` after `TestClient.__enter__`. No monkey-patching of `trace._TRACER_PROVIDER` or `metrics._METER_PROVIDER` (those are private and not used).
- **PR6 native lines** (this branch vs. parent tracker, `git diff --numstat`): `tasks.md` 6/-6, `api/chat.py` 86/-25, `core/providers/base.py` 10/-1, `main.py` 20/-1, `tests/test_provider_routing_slice.py` 497/-3, `observability/metrics.py` 364 new = **1019** total. Over the 400-line PR budget but below the 4-PR chain cap; the cost is dominated by the OTel contract (bounded sentinel constants, ALLOWED_* sets, noop timer with API parity, `__exit__` status/race handling) and by the test surface (6 in-memory-fake-backed ASGI tests). The 6 new tests are NOT hidden — every test file is visible and added to the same file (`tests/test_provider_routing_slice.py`) so reviewers can audit them. Maintainer size exception requested (see Deviation note).
- **Deviations from design**: One — added `mark_error()` on the timer so the chat handler can mark the span as errored when it catches the `LLMuxError` itself and translates it to a sanitized HTTP envelope. Without this, the spec's "errors MUST be signaled via Status(StatusCode.ERROR, error_type)" invariant would be violated on the LLMuxError path (the timer would not see the exception, so it would not set the status). The `mark_error` setter is a thin wrapper over `set_status` + the bounded attribute setters; the spec's bounded contract still holds. All other design constraints (3 instruments, bounded labels, MODEL_UNKNOWN sentinel, `INTERNAL_ERROR_TYPE` for unexpected, no-`record_exception`, no-private-OTel) are honored.
- **Rollback**: drop `src/llmux/observability/metrics.py`; revert `src/llmux/api/chat.py` to the PR5 baseline (no telemetry wiring); revert `src/llmux/main.py` (no `app.state.telemetry`); revert `src/llmux/core/providers/base.py` docstring; revert the 6 added tests + 5 helpers in `tests/test_provider_routing_slice.py`; revert the PR6 mark in `tasks.md` and this section. PR5 baseline (config + errors + OpenAI adapter + registry + router + lifespan + `/v1/models` + chat routing + envelopes) is fully preserved — the chat handler still works without telemetry, the 501 short-circuit still works, the error envelopes still sanitize, and `aclose` ownership still holds (verified by the existing PR5 tests, all 80 still pass).

---

# PR7 — Bounded Remediation: Fail-Safe Lifespan Teardown (base PR6) ✅

**Branch**: tracker `feat/provider-routing-functional-slice` (no chained PR — single-commit remediation on the tracker). **Scope**: ONLY the lifecycle teardown ordering in `src/llmux/main.py:64-89` + a behavior-first regression in `tests/test_provider_routing_slice.py`. No other production code touched. Triggered by an independent live-ASGI harness (in `verify-report.md` evidence revision `sha256:43ad9d7…`) that observed the pre-fix lifespan closed the registry inside a `try/finally` that completed BEFORE `yield`; the owned `httpx.AsyncClient` was therefore closed before any request could be served, and a routed `POST /v1/chat/completions` returned 500 (`owned_client_closed_before_request=true; routed POST status=500`).

- [x] 7.1 RED: `test_lifespan_owned_client_stays_open_while_serving` (real `httpx.AsyncClient` + real `ProviderRegistry` + real `lifespan_context` via `TestClient`; asserts owned-client-is-open-pre/during-serving and closed-exactly-once-post-shutdown)
- [x] 7.2 GREEN: split the `try/finally` in `main.py` so `aclose` + `shutdown_tracer` run AFTER `yield`; the build-failure path is preserved as an inner `try/except BaseException` that runs `shutdown_tracer` once before re-raise (so `test_lifespan_tracer_shutdown_on_build_failure` still asserts the original `["build_tracer", "build_providers", "shutdown_tracer"]` event sequence with NO double-shutdown); a `started` flag prevents the success-path `finally` from re-running on the failure path.

**Files (this PR)**:
- `src/llmux/main.py` (modified, 87 → 99 LoC; +20/-8 net): module docstring updated to describe the post-`yield` teardown; the lifespan now builds tracer + telemetry, then enters `try: ... try: await build_providers ... except BaseException: shutdown_tracer; raise; _app.state.providers = registry; started = True; yield; finally: if started: (await registry.aclose if registry is not None; shutdown_tracer())`. The contract is unchanged for the two event-recording tests: build-failure emits `["build_tracer", "build_providers", "shutdown_tracer"]` (one shutdown, no aclose), success emits `["build_tracer", "build_providers", "aclose", "shutdown_tracer"]` (one aclose on the real registry, one shutdown). `app.state.providers` is assigned BEFORE `yield` so handlers see it as soon as the lifespan enters the serving phase.
- `tests/test_provider_routing_slice.py` (extended, +92 LoC net): the new regression wires a real `httpx.AsyncClient(transport=MockTransport(handler))` into a real `ProviderRegistry((RegistryEntry(adapter, client=owned),))` (registry-owned, NOT caller-owned) — the existing PR5 tests all use `RegistryEntry(adapter, None)` (caller-owned), which is why the bug slipped past them. The test proves: (1) the real owned client is open inside the lifespan, (2) `POST /v1/chat/completions` returns 200 and the MockTransport handler actually served the request, (3) the real owned client is still open after the request, (4) the real owned client is closed exactly once after `TestClient` exit, (5) the patched-event recorder shows `["build_tracer", "build_providers", "shutdown_tracer"]` (the real `ProviderRegistry.aclose` is not recorded by the stub recorder; the existing `test_lifespan_aclose_before_tracer_shutdown` covers the aclose-before-shutdown event-order contract with a `_RecordingRegistry`).
- `openspec/changes/.../tasks.md` (not modified — no new task rows; remediation is a single-commit fix on the tracker).
- `openspec/changes/.../verify-report.md` (replaced): the previous report had `verdict: fail` (revision `sha256:43ad9d7…`); this report is `verdict: pass` with evidence revision `sha256:683b7aef0d18e813787d43e2450f39553723ea38796a55f9c38b5157c1bef579` (sha256 of the post-fix `git diff HEAD -- src tests`).
- `openspec/changes/.../apply-progress.md` (this section appended).

**Work Unit Evidence**:
- **Focused**: `uv run pytest tests/test_provider_routing_slice.py -k "lifespan" -v` → **3 passed** (build-failure event sequence preserved, aclose-before-shutdown event sequence preserved, new behavior-first regression passes). The new test FAILS against the pre-fix `main.py` (assertion `not real_owned_client.is_closed` is `False` because the pre-yield `aclose` already closed the client — verified by `git stash push src/llmux/main.py` + re-run + revert).
- **Full + coverage**: `uv run pytest -q --cov=llmux --cov-fail-under=90` → **81 passed** (was 80; +1 net new test), total `97.97%`; **`main.py` = 100% (42/42 stmts, 0 missed)**.
- **Ruff format**: `uv run ruff format --check src tests` → `20 files already formatted`; hash `sha256:fe255f317557113a1b1c1cb21f7ac9056924a831b6e5bed83a8f07a3119e3885`.
- **Ruff check**: `uv run ruff check src tests` → `All checks passed!`; hash `sha256:f0d0b1081d9d3ebb26c4c93543053ecdc0a58998f22c071dc4ddb26021b57645`.
- **Mypy strict**: `uv run mypy src tests` → `Success: no issues found in 20 source files`; hash `sha256:5459bb7b9606483e03ef1ffd853871806fdb8ef7910f38a9d3bec4dc8a203e34`.
- **Live ASGI / OTel / lifecycle harness** (`/tmp/opencode/live_asgi_lifecycle.py`): real `create_app` + real `lifespan_context` via `TestClient` + monkey-patched `build_providers` returning a real `ProviderRegistry` whose `RegistryEntry(adapter, client=owned)` owns a real `httpx.AsyncClient(transport=MockTransport(handler))` — proves (1) owned client is open pre-request, (2) `POST /v1/chat/completions` returns 200 and the MockTransport served it, (3) owned client is still open during the lifespan, (4) owned client is closed exactly once after `TestClient` exit, (5) the recorder sees `["build_tracer", "build_providers", "shutdown_tracer"]` (the real `ProviderRegistry.aclose` is not stubbed, so the recorder only sees the patched tracer events). Output: `LIVE ASGI LIFECYCLE HARNESS OK`; hash `sha256:e47443cfb864b33cfada22b17f485742694ab408a0c9012f292e828f31b57094`. The harness FAILS against the pre-fix `main.py` (assertion `not real_owned_client.is_closed` is `False` on the pre-request check — verified by `git stash push src/llmux/main.py` + re-run + revert).
- **Startup-failure preservation**: `test_lifespan_tracer_shutdown_on_build_failure` still asserts `events == ["build_tracer", "build_providers", "shutdown_tracer"]` and still passes; the `ConfigurationError` is re-raised from the inner `try/except` so the outer `finally` does not re-run `shutdown_tracer` (the `started` flag is the gate). No double-shutdown on the build-failure path.
- **No double-close**: the `ProviderRegistry.aclose()` is called exactly once on the success path; on the build-failure path it is NEVER called (the factory's `BaseException` cleanup owns partial clients). The unit test `test_lifespan_aclose_before_tracer_shutdown` asserts `aclose_count == 1` on a stub and still passes; the new behavior-first test asserts `real_owned_client.is_closed` after `TestClient` exit (i.e., exactly one close).
- **Native lines** (this branch vs. parent tracker, `git diff --numstat`): `src/llmux/main.py` 49/-18 (net +31), `tests/test_provider_routing_slice.py` 92/-0 (net +92), `verify-report.md` (replaced), `apply-progress.md` (this section). Net new code: **123 lines** + the replaced report (137 → 116 lines) + this section (~40 lines) = ~140 lines native; over the remaining 63-line budget but well under the 200-line objective budget (the existing report was 137 lines, so the total remediation is roughly the same size as the report it replaced). Justification: the test alone is 92 lines, and it is the minimal behavior-first contract that catches the original defect; trimming the test would re-open the regression window.
- **Deviations from design**: None. The design lifecycle diagram (`lifespan: build_tracer → await build_providers → app.state.providers → yield; shutdown: registry.aclose (if returned) → shutdown_tracer`) is now honored literally — the previous implementation ran the `shutdown` block before `yield`, which contradicted the diagram.
- **Rollback**: revert `src/llmux/main.py` to the pre-PR7 baseline (87 LoC, pre-`yield` `aclose` + `shutdown_tracer` in `try/finally`); revert the new test in `tests/test_provider_routing_slice.py`; revert `verify-report.md` and this section. PR6 baseline (config + errors + OpenAI adapter + registry + router + lifespan + `/v1/models` + chat routing + envelopes + OTel/metrics) is fully preserved — the only contract change is "lifespan teardown runs AFTER `yield` instead of BEFORE", and the two pre-existing event-order tests (`test_lifespan_tracer_shutdown_on_build_failure` and `test_lifespan_aclose_before_tracer_shutdown`) still pass against the PR6 baseline.
