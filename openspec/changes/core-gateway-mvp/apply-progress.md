# Apply Progress: Core Gateway MVP — Unit 1

## Change

- **Name**: `core-gateway-mvp`
- **Branch**: `feat/core-gateway-mvp` (base: `docs/foundation` until PR #2 merges)
- **Work unit**: Unit 1 — Tooling foundation + Provider port
- **Mode**: Strict TDD for Phase 2 provider port; pre-TDD for Phase 1 tooling bootstrap
- **Artifact store**: openspec

## Status

10/19 tasks complete. Unit 1 is ready for the next batch.

## Completed Tasks

### Phase 1: Tooling Foundation

- [x] 1.1 Create `pyproject.toml`: package `llmux`, src layout, runtime + dev dependencies, `[tool.pytest.ini_options]`
- [x] 1.2 Generate `uv.lock` via `uv lock` (committed; **excluded** from authored count)
- [x] 1.3 Create `ruff.toml` (line-length 88, target py312, lint/format rules)
- [x] 1.4 Create `.env.example` listing `LLMUX_HOST`/`PORT`/`VERSION`/`PROVIDERS_CONFIGURED`/`OTEL_SERVICE_NAME`/`OTEL_EXPORTER_OTLP_ENDPOINT`
- [ ] 1.5 `Dockerfile` — intentionally deferred; droppable per workload forecast and outside Unit 1 scope

### Phase 2: Provider Port (strict TDD)

- [x] 2.1 TDD row — `ProviderAdapter` Protocol: RED imports + subclasses + 4 members → GREEN Protocol in `src/llmux/core/providers/base.py` → REFACTOR inputs as `Sequence[Mapping[str, object]]`/`Mapping[str, object]`
- [x] 2.2 TDD row — `CompletionResult` (`frozen, slots`, `raw=<empty-mapping factory>`): RED construct/read → GREEN dataclass → REFACTOR
- [x] 2.3 TDD row — `Chunk` (`finish_reason=None`): RED construct/read → GREEN dataclass → REFACTOR
- [x] 2.4 TDD row — `ModelInfo` (`supports_streaming`): RED construct/read → GREEN dataclass → REFACTOR
- [x] 2.5 TDD row — `HealthStatus` (`latency_ms=None, error=None`): RED construct/read → GREEN dataclass → REFACTOR
- [x] 2.6 TDD row — `complete_stream` typing: RED asserts sync method returning `AsyncIterator[Chunk]` (no nested coroutine) → GREEN declaration → REFACTOR

## Files Changed (Unit 1)

| File | Action | What Was Done |
|------|--------|---------------|
| `pyproject.toml` | Created | `llmux` package, src layout, runtime + dev dependency groups, pytest/mypy/hatchling config |
| `uv.lock` | Generated | Locked dependency snapshot; excluded from authored-line budget |
| `ruff.toml` | Created | Line-length 88, target py312, lint/format rules |
| `.env.example` | Created | Runtime + OTel environment variable examples |
| `src/llmux/__init__.py` | Created | Package marker (empty) |
| `src/llmux/core/__init__.py` | Created | Package marker (empty) |
| `src/llmux/core/providers/__init__.py` | Created | Package marker (empty) |
| `src/llmux/core/providers/base.py` | Created | `ProviderAdapter` Protocol + `CompletionResult`/`Chunk`/`ModelInfo`/`HealthStatus` dataclasses |
| `tests/core/test_provider_protocol.py` | Created | Strict-TDD contract tests for the provider port |
| `openspec/changes/core-gateway-mvp/tasks.md` | Updated | Marked Unit 1 tasks `[x]` |

## TDD Cycle Evidence (Phase 2)

All Phase 2 tests were written before production code. The focused test file is `tests/core/test_provider_protocol.py` (11 tests).

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 2.1 `ProviderAdapter` Protocol | `tests/core/test_provider_protocol.py` | Unit | N/A (new) | ✅ Written | ✅ 11 passed | ✅ members declared + subclassable | ✅ typed inputs |
| 2.2 `CompletionResult` | `tests/core/test_provider_protocol.py` | Unit | N/A (new) | ✅ Written | ✅ 11 passed | ✅ required fields + raw override | ✅ frozen/slots |
| 2.3 `Chunk` | `tests/core/test_provider_protocol.py` | Unit | N/A (new) | ✅ Written | ✅ 11 passed | ✅ required fields + finish_reason | ✅ frozen/slots |
| 2.4 `ModelInfo` | `tests/core/test_provider_protocol.py` | Unit | N/A (new) | ✅ Written | ✅ 11 passed | ✅ required fields | ✅ frozen/slots |
| 2.5 `HealthStatus` | `tests/core/test_provider_protocol.py` | Unit | N/A (new) | ✅ Written | ✅ 11 passed | ✅ required + optional fields | ✅ frozen/slots |
| 2.6 `complete_stream` typing | `tests/core/test_provider_protocol.py` | Unit | N/A (new) | ✅ Written | ✅ 11 passed | ✅ signature + stub yields chunks | ✅ sync declaration |

## Work Unit Evidence

| Evidence | Required value |
|---|---|
| Focused test command and exact result | `uv run pytest tests/core -q` → `11 passed` |
| Runtime harness command/scenario and exact result | `uv run pytest -q` → `11 passed` (Unit 1 has no separate runtime boundary; verification is the test suite) |
| Rollback boundary | Drop `pyproject.toml`, `uv.lock`, `ruff.toml`, `.env.example`, `src/llmux/__init__.py`, `src/llmux/core/__init__.py`, `src/llmux/core/providers/__init__.py`, `src/llmux/core/providers/base.py`, `tests/core/*` (no `tests/conftest.py` — Unit 2/app factory scope) |

## Test Evidence

```text
$ uv run pytest tests/core -q
11 passed

$ uv run pytest -q
11 passed

$ uv run ruff check .
All checks passed!

$ uv run mypy src tests
Success: no issues found in 5 source files
```

## Deviations from Design

1. **Dev dependency declaration**: Used `[dependency-groups]` instead of `[project.optional-dependencies]` for dev tools. `uv sync` does not install optional-dependencies by default, but the design's CI commands (`uv run pytest -q`, `uv run ruff check .`) expect dev tools to be present after a plain `uv sync --frozen`. Dependency groups are installed by default in uv and preserve the exact same package set.
2. **No `tests/conftest.py`**: `tests/conftest.py` belongs to Phase 5 (App Factory + Test Harness) and is explicitly excluded from the current batch scope. The Unit 1 rollback boundary in both `tasks.md` and this apply-progress artifact has been reconciled to remove `tests/conftest.py`. Unit 1 tests are pure contract tests and do not need a FastAPI `TestClient` fixture.
3. **No `Dockerfile`**: Task 1.5 is marked droppable in the tasks artifact and was intentionally skipped to keep Unit 1 within the review budget.

## Issues Found

1. `uv lock` initially resolved against CPython 3.14.4 (the system Python). Re-ran with `--python 3.12` to match `requires-python`.
2. First attempt used `[project.optional-dependencies]` for dev tools, but `uv run pytest` then failed because pytest was not installed in the default sync. Switched to `[dependency-groups]`.

## Remaining Tasks

- [ ] 3.1 `Settings` (Pydantic v2 `BaseSettings`)
- [ ] 3.2 `tracing.build_tracer`
- [ ] 4.1 `GET /v1/health`
- [ ] 4.2 `GET /v1/models`
- [ ] 4.3 `POST /v1/chat/completions` 501 (stream=false)
- [ ] 4.4 Chat 501 identical for stream=true and stream-omitted
- [ ] 5.1 `create_app` + `app` export
- [ ] 5.2 `tests/conftest.py`
- [ ] 6.1 `.github/workflows/ci.yml`
- [ ] 6.2 Flip `openspec/config.yaml`
- [ ] 6.3 Flip ADR-0001 status
- [ ] 6.4 Flip ADR-0002 status
- [ ] 6.5 Append `CONTRIBUTING.md` setup block
- [ ] 6.6 Append forecast note to `exploration.md`

## Workload / PR Boundary

- **Mode**: `feature-branch-chain` child slice 1
- **Current work unit**: Unit 1 — Tooling + provider port
- **Boundary**: Starts from the `docs/foundation` base; ends with `ProviderAdapter` Protocol + dataclasses and bootstrapped `uv run pytest`.
- **Target branch**: `feat/core-gateway-mvp` (based on `docs/foundation` until PR #2 merges); the child PR for Unit 1 targets the tracker branch per `feature-branch-chain`.
- **Authored changed lines**: 279 (excluding generated `uv.lock`)
- **Review budget impact**: Well under the 400-line cap; headroom remains for later units.

## Risks

1. `openspec/` directory is untracked in git, so `tasks.md` and `apply-progress.md` updates are workflow-only artifacts and will not appear in the PR diff unless the repository later tracks `openspec/`.
2. The branch base `docs/foundation` is still pending PR #2 merge; retargeting may be needed after that PR lands.

## Next Recommended Phase

`sdd-apply` Unit 2 (API routes + app factory + observability) once Unit 1 is reviewed/merged or the next batch is authorized.
