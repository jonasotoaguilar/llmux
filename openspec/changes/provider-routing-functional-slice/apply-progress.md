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

- [ ] 2.1–2.3 — OpenAI non-streaming adapter (`core/providers/openai.py`).
- [ ] 3.1–3.3 — `ProviderRegistry` + `build_providers` with the fail-fast / `aclose` ownership contract.
- [ ] 4.1–4.6 — Async first-match `select_provider`, fail-safe lifespan, `/v1/models` aggregation.
- [ ] 5.1–5.5 — Chat routing + envelopes (no telemetry).
- [ ] 6.1–6.6 — OTel span, three bounded metrics, `MODEL_UNKNOWN` sentinel, uncaught-exception accounting.
