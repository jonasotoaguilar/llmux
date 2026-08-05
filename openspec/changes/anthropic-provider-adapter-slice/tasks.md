# Tasks: Anthropic Provider Adapter Slice

> **Reslice**: 2-PR → 4-PR → 6-PR feature-branch-chain, each ≤400 lines. 940-line uncommitted PR1 candidate (350 prod + 590 tests, 108 green, 96.13%, Ruff/mypy) re-organized WITHOUT re-implementing or trimming spec/test coverage. `delivery_strategy=auto-chain`, `chain_strategy=feature-branch-chain`, `review_budget_lines=400`, `issue=#20`. PR2 base = tracker; PR3 base = PR2; PR4 base = PR3; PR5 base = PR4; PR6 base = PR5. The former PR4 (≈ 569 authored) was split into PR4 registry dispatch (167), PR5 chat allowlist + live ASGI (332), and PR6 bounded telemetry (73) to stay ≤400 per child.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | PR1 ≈ 140, PR2 ≈ 399, PR3 ≈ 399, PR4 ≈ 167, PR5 ≈ 332, PR6 ≈ 73; total ≈ 1510 |
| 400-line budget risk | High (per-PR isolation enforced) |
| Chained PRs recommended | Yes |
| Suggested split | PR1 settings+.env → PR2 adapter request+protocol+pre-resp errors → PR3 adapter response+errors+models+health → PR4 registry dispatch → PR5 chat max_tokens + live ASGI → PR6 bounded telemetry |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

> **Issue-first**: issue #20 (`status:approved`) blocks all PR merges per `.github/ISSUE_TEMPLATE/feature_request.yml`. All PRs open draft.

## Phase 0 — Issue-First Gate

- [x] 0.1 Open GH feature request #20; link `proposal.md`; wait for `status:approved` — #20 open with `status:approved`.
- [x] 0.2 All PRs stay draft until #20 is approved — approved; children remain draft per chain policy.

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

- [x] 2.1 **RED** `core/providers/anthropic.py`: Protocol + `__init__` + `complete_stream` → `NotImplementedError`; tests `anthropic_adapter_satisfies_protocol` + `anthropic_complete_stream_raises_not_implemented`. Cmd: `pytest -q -k "anthropic_adapter_satisfies_protocol or anthropic_complete_stream_raises"`.
- [x] 2.2 **GREEN** same file: implement class; same cmd passes.
- [x] 2.3 **RED** same file: `complete` request construction (auth, endpoint, system, max_tokens); tests `anthropic_complete_{sends_correct_request,multiple_system_messages_joined,unsupported_role_raises_configuration_error,omitted_max_tokens_defaults_to_1024,caller_override_512}`. Cmd: `pytest -q -k "anthropic_complete_sends or _multiple_system or _unsupported_role or _omitted_max_tokens or _caller_override"`.
- [x] 2.4 **GREEN** same file: implement `_build_request` + `_extract_system` + `_resolve_max_tokens`; same cmd passes.
- [x] 2.5 **RED** same file: pre-response error normalization; 3-case parametrize `anthropic_complete_maps_failures_to_typed_errors` (transport_error, upstream_500, timeout). Cmd: `pytest -q -k anthropic_complete_maps_failures`.
- [x] 2.6 **GREEN** same file: implement try/except in `complete` + `if response.status_code >= 400`; same cmd passes.
- [x] 2.7 **REFACTOR** same file: extract helpers; cmd: `pytest -q -k anthropic`.
- [x] 2.8 **PR2 verify**: `pytest -q --cov=llmux --cov-fail-under=90 && ruff check . && mypy src tests` → 96 passed, 96.29% coverage, ruff clean, mypy clean (actual PR2 verify on `feat/anthropic-provider-adapter-slice-02-adapter-request` @ ae60290). Rollback: revert → request+error code removed; PR1 stays.

## Phase 3 — PR3: Adapter Response + Errors + Models + Health (≈ 345 LoC, base = PR2)

> Code already in 940-line uncommitted PR1 candidate. Replace stub with `_parse_completion` + helpers; add `models()` + `health()` + 7 tests.

- [x] 3.1 **RED** same file: response translation (text-block join, non-text → `UpstreamError`, token counts, stop-reason map); tests `anthropic_complete_{returns_result_with_expected_fields,text_blocks_joined,non_text_block_raises_upstream_error,token_counts_mapped,stop_reason_mapping}` (parametrized). Cmd: `pytest -q -k "anthropic_complete_returns_result or _text_blocks or _non_text or _token_counts or _stop_reason"`.
- [x] 3.2 **GREEN** same file: implement `_parse_completion` + `_coerce_int` + `_map_stop_reason` + `_STOP_REASON_MAP`; replace stub in `complete`; same cmd passes (7 passed).
- [x] 3.3 **RED** same file: `models()` returns configured `ModelInfo`s; test `anthropic_models_returns_configured_models`. Cmd: `pytest -q -k anthropic_models`.
- [x] 3.4 **GREEN** same file: implement `models()`; same cmd passes.
- [x] 3.5 **RED** same file: `health()` `GET {base_url}/` reachability; 2-case parametrize `anthropic_health_reflects_outcome`. Cmd: `pytest -q -k anthropic_health`.
- [x] 3.6 **GREEN** same file: implement `health()`; same cmd passes.
- [x] 3.7 **PR3 verify**: `pytest -q --cov=llmux --cov-fail-under=90 && ruff check . && mypy src tests` → 109 passed, 95.56% coverage, ruff check + format clean, mypy clean (actual PR3 verify @ aade370). Rollback: revert → response+models+health removed; PR2 stays.

## Phase 4 — PR4: Registry Anthropic Dispatch + Ownership (167 authored, base = PR3)

> New work — NOT in 940-line uncommitted PR1 candidate. Former PR4 (≈ 569 authored) split into three children: **PR4 #25** = 4.1-4.3 + 4.6/4.7 (in-tree); **PR5 #26** = 4.4/4.5 + 4.8/4.9 helpers (`_anthropic_env` landed in PR4); **PR6 #27** = 4.10/4.11. Task 4.12 = cumulative verify (final suite).

- [x] 4.1 **RED** `core/providers/registry.py`: `test_build_providers_dispatches_anthropic_slug`. Cmd: `pytest -q -k build_providers_dispatches_anthropic_slug`.
- [x] 4.2 **GREEN** same file: dispatch + factory + cleanup + `RegistryEntry(client=None)` ownership.
- [x] 4.3 **REFACTOR** same file: extract `_build_openai`/`_build_anthropic`.
- [x] 4.4 **RED** `api/chat.py`: `max_tokens: int | None` + `test_chat_{forwards_max_tokens_to_anthropic_adapter,drops_unknown_options,max_tokens_omitted_passes_no_override}`. Cmd: `pytest -q -k max_tokens`.
- [x] 4.5 **GREEN** same file: `_allowlist_options(body)` returns only `max_tokens`; pass to `adapter.complete(..., options=...)`.
- [x] 4.6 **RED rewrite** `test_build_providers_closes_first_client_on_later_failure` to use a truly-unknown slug (`"openai,fake-unknown-slug"`).
- [x] 4.7 **GREEN** same line: same cmd passes.
- [x] 4.8 **RED live ASGI**: 200 envelope, 400 selection miss, 502 upstream, 504 timeout, 501 `stream=true`, `max_tokens=512` on wire, omitted → 1024. Cmd: `pytest -q -k "anthropic_chat or anthropic_live"`.
- [x] 4.9 **GREEN** same file: add `_make_anthropic_adapter_holder` + `_anthropic_env` helpers.
- [x] 4.10 **RED bounded telemetry**: `bounded_providers = {"openai","anthropic","none"}` + `test_telemetry_bounded_anthropic_provider_label`. Cmd: `pytest -q -k bounded`.
- [x] 4.11 **GREEN** same file: same cmd passes.
- [x] 4.12 **PR4 verify**: `pytest -q --cov=llmux --cov-fail-under=90 && ruff check . && mypy src tests` → 122 passed, 95.84% coverage, ruff + format clean, mypy clean (cumulative final state on PR6 @ 5f3915d). Rollback: revert the three former-PR4 children → registry OpenAI-only, chat no `options`; PR1+PR2+PR3 stay.
- [x] 4.13 **Tracker + chain delivered**: tracker **#22** (draft, base=main, `Closes #20`); PR2 **#23** → tracker, PR3 **#24** → #23, PR4 **#25** → #24, PR5 **#26** → #25, PR6 **#27** → #26; all drafts with `Related to #20` + `type:feature`. Children authored: #23 399, #24 399, #25 167, #26 332, #27 73 — all ≤ 400, no `size:exception`. PR Validation + Lint/Types/Tests green on #23-#26 (#27 last check pending at delivery). Tracker #22 remains draft/no-merge; its cumulative diff (969) exceeds 400 by design (aggregator) — `size:exception` intentionally not applied; maintainer decides at integration.

> **Threat matrix**: only "Runtime provider routing" applies (covered by 4.8); other rows `N/A` per `design.md`. No `ARCHITECTURE.md`, no new ADR, no new dep. Out of scope: streaming/SSE, tool use, prompt caching, multimodal, model alias, cost, auth-validity health, fallback, retries, new error class, new metric.

## Strict-TDD Cycle Evidence

The implementation phases followed RED → GREEN → triangulation with the
previous suite retained as the safety net. `N/A` denotes a bookkeeping,
documentation, refactor, or verification task rather than a new behavior
cycle. The phase reports and command results are also preserved in the
Engram apply-progress artifact.

| Task | RED | GREEN | TRIANGULATE | SAFETY NET |
|------|-----|-------|-------------|------------|
| 0.1 | N/A — issue gate | Issue #20 approved | GitHub issue labels/state | No code changed |
| 0.2 | N/A — delivery gate | Children #23–#27 draft; #21 merged after approval | PR metadata and bases | No code changed |
| 1.1 | Settings cases failed before validator | Focused settings cases passed | Empty key, empty models, invalid URL | Existing suite |
| 1.2 | 1.1 RED cases | Same focused command passed | Default and enabled-provider paths | Existing suite |
| 1.3 | N/A — environment documentation | `.env.example` block present | Settings names match config fields | Full PR1 suite |
| 1.4 | N/A — fixture wiring | Anthropic fixture paths passed | Clean-env isolation | Full PR1 suite |
| 1.5 | Two causal pre-existing tests failed after validation change | 86-test PR1 suite passed | JSON/empty settings and unknown-slug failure | Coverage gate |
| 1.6 | N/A — verification task | 86 passed, 98.05% coverage | Ruff and mypy passed | PR1 suite and coverage gate |
| 2.1 | Protocol/stream tests failed against stubs | Protocol and stream tests passed | Runtime-checkable Protocol surface | PR1 suite |
| 2.2 | 2.1 RED cases | Adapter class tests passed | Constructor and four-method surface | PR1 suite |
| 2.3 | Five request-shape cases failed | Five request tests passed | Headers, system join, role rejection, token default/override | PR1 suite |
| 2.4 | 2.3 RED cases | Request-construction tests passed | Captured wire request assertions | PR1 suite |
| 2.5 | Three typed-error cases failed | Three error cases passed | Transport, HTTP 500, timeout | PR1 suite |
| 2.6 | 2.5 RED cases | Error normalization passed | Body discard and typed hierarchy | PR1 suite |
| 2.7 | N/A — refactor | Anthropic focused suite passed | Helpers preserved request behavior | PR1 + PR2 suite |
| 2.8 | N/A — verification task | 96 passed, 96.29% coverage | Ruff and mypy passed | PR1 + PR2 suite |
| 3.1 | Five response cases failed against 2xx stub | Seven response tests passed | Text, non-text, tokens, three stop reasons | 96-test suite |
| 3.2 | 3.1 RED cases | Parser and mapping tests passed | Malformed and missing-content cases | 96-test suite |
| 3.3 | Models test failed against stub | Configured-model test passed | ModelInfo fields and provider label | 96-test suite |
| 3.4 | 3.3 RED case | Models implementation passed | Multiple configured models | 96-test suite |
| 3.5 | Two health cases failed against stub | Two health cases passed | Reachability success and transport failure | 96-test suite |
| 3.6 | 3.5 RED cases | Health implementation passed | No-auth reachability behavior | 96-test suite |
| 3.7 | N/A — verification task | 109 passed, 95.56% coverage | Ruff, format, and mypy passed | PR1–PR3 suite |
| 4.1 | Anthropic slug dispatch failed as unknown | Dispatch test passed | Registry factory selection | 109-test suite |
| 4.2 | 4.1 RED case | Registry construction passed | Factory cleanup and ownership marker | 109-test suite |
| 4.3 | N/A — refactor | Registry suite passed | OpenAI behavior retained | 109-test suite |
| 4.4 | Two allowlist cases failed | Allowlist focused suite passed | Forward, drop, and omission cases | 109-test suite |
| 4.5 | 4.4 RED cases | Chat forwarding passed | `max_tokens` validation and options shape | 109-test suite |
| 4.6 | N/A — regression-test rewrite | Unknown-slug regression passed | Truly unknown second slug | 109-test suite |
| 4.7 | 4.6 RED case | Registry cleanup suite passed | Failure closes earlier client exactly once | 109-test suite |
| 4.8 | RED carried by dispatch/allowlist seams | Seven live ASGI cases passed | 200/400/501/502/504 and wire defaults | 109-test suite |
| 4.9 | N/A — test harness helper | Live ASGI harness passed | Production registry construction path | 109-test suite |
| 4.10 | RED carried by prior routing seams | Bounded telemetry cases passed | Provider/model/outcome/error-type sets | 121-test suite |
| 4.11 | 4.10 RED path | Anthropic telemetry label passed | Span and metric dimensions | 121-test suite |
| 4.12 | N/A — verification task | 122 passed, 95.84% coverage | Ruff, format, and mypy passed | Full cumulative suite |
| 4.13 | N/A — delivery bookkeeping | Chain checks and task state passed | PR bases, labels, issue approval, budgets | Full cumulative suite |

### Post-verification assertion remediation

The direct follow-up tightened two inherited telemetry tests so they cannot
pass vacuously: bounded-label checks now require at least one point per
metric, and the success path explicitly requires zero error points. The
remediation is intentionally outside RDD and is verified by the direct test
commands recorded after this artifact was written.
