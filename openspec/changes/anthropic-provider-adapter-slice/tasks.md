# Tasks: Anthropic Provider Adapter Slice

> **Reslice**: 2-PR → 4-PR feature-branch-chain, each ≤400 lines. 940-line uncommitted PR1 candidate (350 prod + 590 tests, 108 green, 96.13%, Ruff/mypy) re-organized WITHOUT re-implementing or trimming spec/test coverage. `delivery_strategy=auto-chain`, `chain_strategy=feature-branch-chain`, `review_budget_lines=400`, `issue=#20`. PR2 base = PR1; PR3 base = PR2; PR4 base = PR3.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | PR1 ≈ 140, PR2 ≈ 400, PR3 ≈ 345, PR4 ≈ 305; total ≈ 1190 |
| 400-line budget risk | High (per-PR isolation enforced) |
| Chained PRs recommended | Yes |
| Suggested split | PR1 settings+.env → PR2 adapter request+protocol+pre-resp errors → PR3 adapter response+errors+models+health → PR4 registry+chat+ASGI+telemetry |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

> **Issue-first**: issue #20 (`status:approved`) blocks all PR merges per `.github/ISSUE_TEMPLATE/feature_request.yml`. All PRs open draft.

## Phase 0 — Issue-First Gate

- [ ] 0.1 Open GH feature request #20; link `proposal.md`; wait for `status:approved`.
- [ ] 0.2 All four PRs stay draft until #20 is approved.

## Phase 1 — PR1: Settings + .env (≈ 140 LoC, base = main)

> Code already in 940-line uncommitted PR1 candidate. Cherry-pick only the config-side commit.
>
> **Reorganized on `feat/anthropic-provider-adapter-slice-01-config`**: 173 insertions / 3 deletions across 4 files (no `anthropic.py`, no adapter behavior tests, no registry/chat/telemetry). The full 940-line candidate is preserved at `stash@{0}` (msg `anpr-adapter-slice-PR1-restructure-backup`) for PR2/PR3 cherry-pick.

- [x] 1.1 **RED** `config.py`: `ANTHROPIC_*` fields + validators; tests `test_anthropic_settings_{valid,default,invalid_raises_configuration_error}` (parametrized empty_key/empty_models/invalid_url). Cmd: `pytest -q -k anthropic_settings`.
- [x] 1.2 **GREEN** same file: implement fields + validator; same cmd passes.
- [x] 1.3 **`.env.example`**: append `ANTHROPIC_*` block incl. `ANTHROPIC_TIMEOUT_S=30`.
- [x] 1.4 **Fixture**: add `_ANTHROPIC_ENV` + `_enable_anthropic` + autouse `_clean_env` extension.
- [x] 1.5 **Existing-test compatibility** (causally required by 1.1/1.2): `tests/test_unit_2.py::test_settings_providers_accepts_json_and_empty` adds `ANTHROPIC_API_KEY` + `ANTHROPIC_MODELS` monkeypatches; `tests/test_provider_routing_slice.py::test_build_providers_closes_first_client_on_later_failure` rewrites the 2nd slug to `openai,fake-unknown-slug` (the same rewrite PR2 task 2.7 calls for — moved up so the test invariant stays valid after `anthropic` becomes a valid Settings slug).
- [x] 1.6 **PR1 verify**: `pytest -q --cov=llmux --cov-fail-under=90 && ruff check . && mypy src tests` → 86 passed, 98.05% coverage, ruff clean, mypy clean. Rollback: revert → `ANTHROPIC_*` + `.env` block vanish; OpenAI unchanged.

## Phase 2 — PR2: Adapter Request + Protocol + Pre-Response Errors (≈ 400 LoC, base = PR1)

> Code already in 940-line uncommitted PR1 candidate. Extract request-construction side + 8 tests + 2 helpers.

- [ ] 2.1 **RED** `core/providers/anthropic.py`: Protocol + `__init__` + `complete_stream` → `NotImplementedError`; tests `anthropic_adapter_satisfies_protocol` + `anthropic_complete_stream_raises_not_implemented`. Cmd: `pytest -q -k "anthropic_adapter_satisfies_protocol or anthropic_complete_stream_raises"`.
- [ ] 2.2 **GREEN** same file: implement class; same cmd passes.
- [ ] 2.3 **RED** same file: `complete` request construction (auth, endpoint, system, max_tokens); tests `anthropic_complete_{sends_correct_request,multiple_system_messages_joined,unsupported_role_raises_configuration_error,omitted_max_tokens_defaults_to_1024,caller_override_512}`. Cmd: `pytest -q -k "anthropic_complete_sends or _multiple_system or _unsupported_role or _omitted_max_tokens or _caller_override"`.
- [ ] 2.4 **GREEN** same file: implement `_build_request` + `_extract_system` + `_resolve_max_tokens`; same cmd passes.
- [ ] 2.5 **RED** same file: pre-response error normalization; 4-case parametrize `anthropic_complete_maps_failures_to_typed_errors` (transport_error, upstream_500, upstream_500_discards_body, timeout). Cmd: `pytest -q -k anthropic_complete_maps_failures`.
- [ ] 2.6 **GREEN** same file: implement try/except in `complete` + `if response.status_code >= 400`; same cmd passes.
- [ ] 2.7 **REFACTOR** same file: extract helpers; cmd: `pytest -q -k anthropic`.
- [ ] 2.8 **PR2 verify**: `pytest -q --cov=llmux --cov-fail-under=90 && ruff check . && mypy src tests`. Rollback: revert → request+error code removed; PR1 stays.

## Phase 3 — PR3: Adapter Response + Errors + Models + Health (≈ 345 LoC, base = PR2)

> Code already in 940-line uncommitted PR1 candidate. Replace stub with `_parse_completion` + helpers; add `models()` + `health()` + 7 tests.

- [ ] 3.1 **RED** same file: response translation (text-block join, non-text → `UpstreamError`, token counts, stop-reason map); tests `anthropic_complete_{returns_result_with_expected_fields,text_blocks_joined,non_text_block_raises_upstream_error,token_counts_mapped,stop_reason_mapping}` (parametrized). Cmd: `pytest -q -k "anthropic_complete_returns_result or _text_blocks or _non_text or _token_counts or _stop_reason"`.
- [ ] 3.2 **GREEN** same file: implement `_parse_completion` + `_coerce_int` + `_map_stop_reason` + `_STOP_REASON_MAP`; replace stub in `complete`; same cmd passes.
- [ ] 3.3 **RED** same file: `models()` returns configured `ModelInfo`s; test `anthropic_models_returns_configured_models`. Cmd: `pytest -q -k anthropic_models`.
- [ ] 3.4 **GREEN** same file: implement `models()`; same cmd passes.
- [ ] 3.5 **RED** same file: `health()` `GET {base_url}/` reachability; 2-case parametrize `anthropic_health_reflects_outcome`. Cmd: `pytest -q -k anthropic_health`.
- [ ] 3.6 **GREEN** same file: implement `health()`; same cmd passes.
- [ ] 3.7 **PR3 verify**: `pytest -q --cov=llmux --cov-fail-under=90 && ruff check . && mypy src tests`. Rollback: revert → response+models+health removed; PR2 stays.

## Phase 4 — PR4: Registry + Chat + ASGI + Telemetry + Mid-Build Cleanup (≈ 305 LoC, base = PR3)

> New work — NOT in 940-line uncommitted PR1 candidate.

- [ ] 4.1 **RED** `core/providers/registry.py`: `test_build_providers_dispatches_anthropic_slug`. Cmd: `pytest -q -k build_providers_dispatches_anthropic_slug`.
- [ ] 4.2 **GREEN** same file: dispatch + factory + cleanup + `RegistryEntry(client=None)` ownership.
- [ ] 4.3 **REFACTOR** same file: extract `_build_openai`/`_build_anthropic`.
- [ ] 4.4 **RED** `api/chat.py`: `max_tokens: int | None` + `test_chat_{forwards_max_tokens_to_anthropic_adapter,drops_unknown_options,max_tokens_omitted_passes_no_override}`. Cmd: `pytest -q -k max_tokens`.
- [ ] 4.5 **GREEN** same file: `_allowlist_options(body)` returns only `max_tokens`; pass to `adapter.complete(..., options=...)`.
- [ ] 4.6 **RED rewrite** `test_build_providers_closes_first_client_on_later_failure` to use a truly-unknown slug (`"openai,fake-unknown-slug"`).
- [ ] 4.7 **GREEN** same line: same cmd passes.
- [ ] 4.8 **RED live ASGI**: 200 envelope, 400 selection miss, 502 upstream, 504 timeout, 501 `stream=true`, `max_tokens=512` on wire, omitted → 1024. Cmd: `pytest -q -k "anthropic_chat or anthropic_live"`.
- [ ] 4.9 **GREEN** same file: add `_make_anthropic_adapter_holder` + `_anthropic_env` helpers.
- [ ] 4.10 **RED bounded telemetry**: `bounded_providers = {"openai","anthropic","none"}` + `test_telemetry_bounded_anthropic_provider_label`. Cmd: `pytest -q -k bounded`.
- [ ] 4.11 **GREEN** same file: same cmd passes.
- [ ] 4.12 **PR4 verify**: `pytest -q --cov=llmux --cov-fail-under=90 && ruff check . && mypy src tests`. Rollback: revert → registry OpenAI-only, chat no `options`; PR1+PR2+PR3 stay.
- [ ] 4.13 **Tracker + chain**: draft tracker → main; PR1 → tracker, PR2 → PR1, PR3 → PR2, PR4 → PR3; retarget in order, merge in order, tracker last.

> **Threat matrix**: only "Runtime provider routing" applies (covered by 4.8); other rows `N/A` per `design.md`. No `ARCHITECTURE.md`, no new ADR, no new dep. Out of scope: streaming/SSE, tool use, prompt caching, multimodal, model alias, cost, auth-validity health, fallback, retries, new error class, new metric.
