# Apply Progress: Core Gateway MVP — Unit 2, First Slice (Runtime)

## Change

- **Name**: `core-gateway-mvp`
- **Branch (this slice)**: `feat/core-gateway-runtime` (feature-branch-chain child of `feat/core-gateway-mvp`)
- **Mode**: Strict TDD for all rows with non-trivial logic
- **Scope split**: Uncommitted Unit 2 split into two sequential feature-branch-chain slices. This file tracks the **first slice** (Runtime: Settings + Observability). API routes (4.1–5.2) are preserved in a recoverable patch for the second slice.
- **Child slice archive**: `/tmp/opencode/llmux-api-slice/` (tarball at `/tmp/opencode/llmux-api-slice.tar.gz`)

## Status

**12/19 tasks complete** in this slice (Phase 1–2 from prior batch, Phase 3 from this slice). Tasks 4.1–5.2 are pending in the API child slice.

## Completed Tasks

### Phase 1: Tooling Foundation

- [x] 1.1 Create `pyproject.toml`: package `llmux`, src layout, runtime + dev dependencies, `[tool.pytest.ini_options]`
- [x] 1.2 Generate `uv.lock` via `uv lock` (committed; **excluded** from authored count)
- [x] 1.3 Create `ruff.toml` (line-length 88, target py312, lint/format rules)
- [x] 1.4 Create `.env.example` listing `LLMUX_HOST`/`PORT`/`VERSION`/`PROVIDERS_CONFIGURED`/`OTEL_SERVICE_NAME`/`OTEL_EXPORTER_OTLP_ENDPOINT`
- [ ] 1.5 `Dockerfile` — intentionally deferred; droppable per workload forecast

### Phase 2: Provider Port (strict TDD)

- [x] 2.1 TDD row — `ProviderAdapter` Protocol
- [x] 2.2 TDD row — `CompletionResult`
- [x] 2.3 TDD row — `Chunk`
- [x] 2.4 TDD row — `ModelInfo`
- [x] 2.5 TDD row — `HealthStatus`
- [x] 2.6 TDD row — `complete_stream` typing

### Phase 3: Settings + Observability (this slice)

- [x] 3.1 TDD row — `Settings` (Pydantic v2 `BaseSettings`)
- [x] 3.2 TDD row — `tracing.build_tracer`

### Phase 4: API Routes (pending — child slice)

- [ ] 4.1 TDD row — `GET /v1/health`
- [ ] 4.2 TDD row — `GET /v1/models`
- [ ] 4.3 TDD row — `POST /v1/chat/completions` 501 (stream=false)
- [ ] 4.4 TDD row — chat 501 identical for `stream=true` and `stream`-omitted

### Phase 5: App Factory + Test Harness (pending — child slice)

- [ ] 5.1 TDD row — `create_app` + `app` export
- [ ] 5.2 Create `tests/conftest.py`

## Files Changed

### Unit 1 (preserved from prior batch)

| File | Action | What Was Done |
|------|--------|---------------|
| `pyproject.toml` | Created | `llmux` package, src layout, runtime + dev dependency groups, pytest/mypy/hatchling config |
| `uv.lock` | Generated | Locked dependency snapshot; excluded from authored-line budget |
| `ruff.toml` | Created | Line-length 88, target py312, lint/format rules |
| `.env.example` | Created | Runtime + OTel environment variable examples |
| `src/llmux/__init__.py` | Created | Package marker (empty) |
| `src/llmux/core/__init__.py` | Created | Package marker (empty) |
| `src/llmux/core/providers/__init__.py` | Created | Package marker (empty) |
| `src/llmux/core/providers/base.py` | Created | `ProviderAdapter` Protocol + dataclasses |
| `tests/core/test_provider_protocol.py` | Created | Strict-TDD contract tests for the provider port |

### Unit 2, First Slice — Runtime (this batch)

| File | Action | What Was Done |
|------|--------|---------------|
| `src/llmux/config.py` | Created | Pydantic v2 `BaseSettings` with env-var aliases, JSON-or-comma parser, port range validation |
| `src/llmux/observability/tracing.py` | Created | `build_tracer(settings)` no-op default + OTLP/HTTP exporter + `BatchSpanProcessor` + `shutdown_tracer()` |
| `tests/test_unit_2.py` | Created | 6 focused tests: 3 Settings + 3 Tracing |
| `openspec/changes/core-gateway-mvp/tasks.md` | Updated | Marked only Phase 3 tasks `[x]`; 4.1–5.2 remain unchecked |
| `openspec/changes/core-gateway-mvp/apply-progress.md` | Updated | Scoped to first slice |

### Unit 2, Second Slice — API (preserved in patch)

The following files implement Phase 4–5 and are preserved in `/tmp/opencode/llmux-api-slice/` for the child branch:

| File | Lines |
|------|-------|
| `src/llmux/api/chat.py` | 38 |
| `src/llmux/api/health.py` | 17 |
| `src/llmux/api/models.py` | 12 |
| `src/llmux/main.py` | 34 |
| `tests/conftest.py` | 31 |
| `tests/test_unit_2.py` (original) | 229 |

## TDD Cycle Evidence

### Phase 3 (this slice)

| Task | Test File | RED | GREEN | REFACTOR |
|------|-----------|-----|-------|----------|
| 3.1 `Settings` | `tests/test_unit_2.py::test_settings_*` | ✅ defaults + JSON list + empty + out-of-range written | ✅ all 3 settings tests pass | ✅ combined JSON-or-comma `field_validator(mode="before")` |
| 3.2 `tracing.build_tracer` | `tests/test_unit_2.py::test_build_tracer_*` | ✅ monkeypatched `set_tracer_provider` capture + assertions | ✅ all 3 tracing tests pass | ✅ removed explicit `isinstance(provider, TracerProvider)` from no-op test, kept it on the SDK path only |

## Work Unit Evidence

### Focused test command and exact result
`uv run pytest tests/test_unit_2.py -q` → `6 passed`

### Full test command and exact result
`uv run pytest -q` → `17 passed` (11 from Unit 1 + 6 from this slice)

### Coverage command and exact result
`uv run pytest -q --cov=llmux --cov-fail-under=90` → `17 passed`

### Ruff command and exact result
`uv run ruff check .` → `All checks passed!`

### Mypy command and exact result
`uv run mypy src tests` → `Success: no issues found in 7 source files`

### Rollback boundary
Drop `src/llmux/config.py`, `src/llmux/observability/`, `tests/test_unit_2.py` — restores to end-of-Unit-1 state. None of these modules are imported from Unit 1's source.

### Authored lines (this slice)

| File | Lines |
|------|-------|
| `src/llmux/config.py` | 41 |
| `src/llmux/observability/tracing.py` | 31 |
| `tests/test_unit_2.py` | 101 |
| **Total** | **173** |

### PR Delta Accounting vs `origin/feat/core-gateway-mvp`

Remote parent confirmed: contains Unit 1 via merged PR #4 (`dd2ecf2`).

| Source | Additions | Deletions | Total |
|--------|-----------|-----------|-------|
| `apply-progress.md` | 110 | 66 | 176 |
| `tasks.md` | 3 | 3 | 6 |
| New source/tests (3 files) | 173 | 0 | 173 |
| **Candidate changed-line workload** | **286** | **69** | **355** |

355 changed lines, well under 400. Do not double-count pre-existing file lengths as delta.

## Remaining Tasks (Child Slice)

- [ ] 1.5 `Dockerfile` — deferred, droppable
- [ ] 4.1 `GET /v1/health`
- [ ] 4.2 `GET /v1/models`
- [ ] 4.3 `POST /v1/chat/completions` 501
- [ ] 4.4 Chat 501 identical across stream modes
- [ ] 5.1 `create_app` + `app` export
- [ ] 5.2 `tests/conftest.py`
- [ ] 6.1 `.github/workflows/ci.yml`
- [ ] 6.2 Flip `openspec/config.yaml`
- [ ] 6.3 Flip ADR-0001 status
- [ ] 6.4 Flip ADR-0002 status
- [ ] 6.5 Append `CONTRIBUTING.md` setup block
- [ ] 6.6 Append forecast note to `exploration.md`

## Deviations from Design

### This slice

1. **`Settings.llmux_providers_configured` needs `NoDecode`**: pydantic-settings 2.14 auto-decodes `list[str]` fields from JSON before the `field_validator(mode="before")` runs. Mitigated with `Annotated[list[str], NoDecode, Field(...)]`.

2. **No `__init__.py` files in `src/llmux/observability/`**: Python 3.12 namespace packages handle it.

3. **Test consolidation**: Tests in one file (`test_unit_2.py`) for line-budget efficiency.

## Restore Instructions (Child Slice)

```bash
# On the child branch (feat/core-gateway-api or similar):
tar xzf /tmp/opencode/llmux-api-slice.tar.gz -C /home/jona/projects/llmux
# Then restore test_unit_2.py (replaces the runtime-only version):
cp -a /tmp/opencode/api-slice-repack/tests/test_unit_2.py tests/test_unit_2.py
```
