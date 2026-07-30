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
