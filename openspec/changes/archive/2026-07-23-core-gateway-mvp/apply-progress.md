# Apply Progress: Core Gateway MVP — Full Unit 2 (Runtime + API) + Unit 3 Activation

## Change

- **Name**: `core-gateway-mvp`
- **Branch (this slice)**: `ci/core-gateway-activation` (stacked child of `feat/core-gateway-mvp` per `stacked-to-main` chain strategy)
- **Mode**: Strict TDD for all rows with non-trivial logic
- **Scope split**: Unit 2 was originally split into two sequential feature-branch-chain slices. Both landed on `feat/core-gateway-mvp` (PRs #4, #5, #6). This `ci/core-gateway-activation` branch is the **final activation** stacked child — Phase 6 (CI, OpenSpec config, ADRs, docs) + deferred 1.5 Dockerfile.

## Status

**26/26 tasks complete** — change ready for `sdd-verify`, then `sdd-archive`.

| Unit | Tasks complete | Branch | Status |
|------|----------------|--------|--------|
| Unit 1 (Tooling + provider port) | 1.1–1.4, 2.1–2.6 = 10/10 | `feat/core-gateway-tooling` → `feat/core-gateway-mvp` (PR #4) | merged |
| Unit 2 first slice (Runtime: Settings + Observability) | 3.1, 3.2 = 2/2 | `feat/core-gateway-runtime` → `feat/core-gateway-mvp` (PR #5) | merged |
| Unit 2 second slice (API + app factory) | 4.1–4.4, 5.1, 5.2 = 6/6 | `feat/core-gateway-api` → `feat/core-gateway-mvp` (PR #6) | merged |
| Unit 3 (Activation: CI, ADRs, docs, Dockerfile) | 1.5, 6.1–6.6 = 7/7 | `ci/core-gateway-activation` (this branch) | uncommitted — this slice |

## Completed Tasks (cumulative)

### Phase 1: Tooling Foundation

- [x] 1.1 Create `pyproject.toml`: package `llmux`, src layout, runtime + dev dependencies, `[tool.pytest.ini_options]`
- [x] 1.2 Generate `uv.lock` via `uv lock` (committed; **excluded** from authored count)
- [x] 1.3 Create `ruff.toml` (line-length 88, target py312, lint/format rules)
- [x] 1.4 Create `.env.example` listing `LLMUX_HOST`/`PORT`/`VERSION`/`PROVIDERS_CONFIGURED`/`OTEL_SERVICE_NAME`/`OTEL_EXPORTER_OTLP_ENDPOINT`
- [x] 1.5 `Dockerfile` (Unit 3) — multi-stage, python:3.12-slim, non-root user, healthcheck on `/v1/health`

### Phase 2: Provider Port (strict TDD)

- [x] 2.1 TDD row — `ProviderAdapter` Protocol
- [x] 2.2 TDD row — `CompletionResult`
- [x] 2.3 TDD row — `Chunk`
- [x] 2.4 TDD row — `ModelInfo`
- [x] 2.5 TDD row — `HealthStatus`
- [x] 2.6 TDD row — `complete_stream` typing

### Phase 3: Settings + Observability (Unit 2 first slice)

- [x] 3.1 TDD row — `Settings` (Pydantic v2 `BaseSettings`)
- [x] 3.2 TDD row — `tracing.build_tracer`

### Phase 4: API Routes (Unit 2 second slice, strict TDD)

- [x] 4.1 TDD row — `GET /v1/health`
- [x] 4.2 TDD row — `GET /v1/models`
- [x] 4.3 TDD row — `POST /v1/chat/completions` 501 (stream=false)
- [x] 4.4 TDD row — chat 501 identical for `stream=true` and `stream`-omitted

### Phase 5: App Factory + Test Harness (Unit 2 second slice)

- [x] 5.1 TDD row — `create_app` + `app` export
- [x] 5.2 Create `tests/conftest.py`

### Phase 6: CI + Config/ADR/Docs Deltas (Unit 3, this slice)

- [x] 6.1 Create `.github/workflows/ci.yml`: `uv sync --frozen` → `ruff check .` → `mypy src tests` → `pytest -q --cov=llmux --cov-fail-under=90`
- [x] 6.2 Flip `openspec/config.yaml` (`strict_tdd: true`, `detected_runner: pytest`, `test_command`, `coverage_threshold: 90`); update `context:` block
- [x] 6.3 Flip ADR-0001 status: `Proposed` → `Accepted`
- [x] 6.4 Flip ADR-0002 status: `Proposed` → `Accepted`
- [x] 6.5 Append `CONTRIBUTING.md` Development Setup block (3 commands: `uv sync` / `uv run pytest` / `uv run uvicorn llmux.main:app`)
- [x] 6.6 Append §6 forecast note to `openspec/changes/core-gateway-mvp/exploration.md`: 501 chat + empty `/v1/models` are contract-correct stubs, not Phase-1 closure (cross-ref proposal Acceptance Boundary)

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

### Unit 2, First Slice — Runtime (preserved from prior batch)

| File | Action | What Was Done |
|------|--------|---------------|
| `src/llmux/config.py` | Created | Pydantic v2 `BaseSettings` with env-var aliases, JSON-or-comma parser, port range validation |
| `src/llmux/observability/tracing.py` | Created | `build_tracer(settings)` no-op default + OTLP/HTTP exporter + `BatchSpanProcessor` + `shutdown_tracer()` |
| `tests/test_unit_2.py` | Created | 6 focused tests: 3 Settings + 3 Tracing |

### Unit 2, Second Slice — API (preserved from prior batch)

| File | Action | What Was Done |
|------|--------|---------------|
| `src/llmux/api/chat.py` | Created | `POST /v1/chat/completions` 501 stub, `ChatMessage`/`ChatCompletionRequest`, single code path, no-fake-SSE |
| `src/llmux/api/health.py` | Created | `GET /v1/health` gateway-native: `status`/`version`/`providers_configured` from `app.state.settings` |
| `src/llmux/api/models.py` | Created | `GET /v1/models` OpenAI `{object:"list", data:[]}` |
| `src/llmux/main.py` | Created | `create_app(settings)` factory: resolve Settings → store on state → mount `/v1/*` → wire OTel lifespan → export `app` |
| `tests/conftest.py` | Created | `app` fixture + `client` fixture (TestClient) |
| `tests/test_unit_2.py` | Modified | Merged: **16 tests** (3 Settings + 3 Tracing + 2 health + 1 models + 1×3 chat + 3 app factory + 1 conftest) |

### Unit 3 — Activation (this slice)

| File | Action | What Was Done |
|------|--------|---------------|
| `.github/workflows/ci.yml` | Created | Single job: install uv → sync frozen → ruff check → mypy → pytest with 90% coverage gate |
| `Dockerfile` | Created | Multi-stage build (build: uv sync, runtime: uvicorn), non-root `llmux` user, healthcheck on `/v1/health` |
| `CONTRIBUTING.md` | Modified | 3-command development setup; Dashboard/DB stack kept as roadmap notes |
| `docs/adr/0001-modular-monolith-topology.md` | Modified | Status: `Proposed` → `Accepted` |
| `docs/adr/0002-provider-abstraction-pattern.md` | Modified | Status: `Proposed` → `Accepted` |
| `docs/adr/README.md` | Modified | ADR index status columns updated |
| `openspec/config.yaml` | Modified | `strict_tdd: true`; `testing:` filled (pytest/ruff/mypy); `apply.tdd: true` + commands; `verify.coverage_threshold: 90` |
| `openspec/changes/core-gateway-mvp/exploration.md` | Modified | §6 blockquote: 501 chat + empty `/v1/models` are contract-correct stubs, not Phase-1 closure |
| `openspec/changes/core-gateway-mvp/tasks.md` | Modified | Marked 1.5 + 6.1–6.6 as `[x]` |
| `openspec/changes/core-gateway-mvp/apply-progress.md` | Modified | This file — Unit-3 evidence appended below; prior Unit-1/Unit-2 evidence preserved |

## TDD Cycle Evidence

### Phase 3 (Unit 2 first slice — preserved)

| Task | Test File | RED | GREEN | REFACTOR |
|------|-----------|-----|-------|----------|
| 3.1 `Settings` | `tests/test_unit_2.py::test_settings_*` | ✅ defaults + JSON list + empty + out-of-range written | ✅ all 3 settings tests pass | ✅ combined JSON-or-comma `field_validator(mode="before")` |
| 3.2 `tracing.build_tracer` | `tests/test_unit_2.py::test_build_tracer_*` | ✅ monkeypatched `set_tracer_provider` capture + assertions | ✅ all 3 tracing tests pass | ✅ removed explicit `isinstance(provider, TracerProvider)` from no-op test, kept it on the SDK path only |

### Phase 4–5 (Unit 2 second slice — preserved)

Strict TDD applied per row; full evidence in the merged `test_unit_2.py` (16 tests: 3 Settings + 3 Tracing + 2 health + 1 models + 1×3 chat + 3 app factory + 1 conftest). All 16 tests green.

### Phase 6 (Unit 3, this slice)

This slice is config/docs/infra — no production logic, no TDD rows. Runtime/build/format/type evidence is below.

## Work Unit Evidence (Unit 3 — this slice)

### Focused test command and exact result
`uv run pytest -q` → `27 passed, 1 warning in 0.08s`

### Full test command and exact result (coverage gate)
`uv run pytest -q --cov=llmux --cov-fail-under=90` → `27 passed`, `Total coverage: 97.78%` (required ≥ 90% reached)

### Ruff commands and exact results
`uv run ruff format .` → `14 files left unchanged` (no mutations)
`uv run ruff check .` → `All checks passed!`

### Mypy command and exact result
`uv run mypy src tests` → `Success: no issues found in 14 source files`

### Runtime harness command/scenario and exact result
`docker build -t llmux-activation-test .` → `sha256:e69dcb02…` (succeeded)
`docker run --rm -p 18000:8000 llmux-activation-test` + `curl http://127.0.0.1:18000/v1/health` → `{"status":"ok","version":"0.1.0","providers_configured":[]}` (200)
`curl http://127.0.0.1:18000/v1/models` → `{"object":"list","data":[]}` (200)
`curl -X POST http://127.0.0.1:18000/v1/chat/completions -d '{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}'` → `{"error":{"message":"Chat completions are not implemented","type":"not_implemented_error","param":null,"code":"not_implemented"}}` (501, `application/json`, no SSE)

### YAML / config validation
`python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` → `ci.yml: valid YAML`
`hadolint Dockerfile` → `1 warning` (DL3008: apt versions not pinned; intentional, accepted; no errors)

### Rollback boundary
Drop `.github/workflows/ci.yml`, `Dockerfile`, revert `CONTRIBUTING.md`, revert `docs/adr/0001-*.md` + `0002-*.md` + `README.md` (status flips), revert `openspec/config.yaml` (strict_tdd → false), revert the §6 blockquote in `exploration.md`, revert `tasks.md` (1.5/6.1–6.6 back to `[ ]`). Phase-1–5 source/tests untouched → runtime + tests stay green. No data/migration/auth risk.

## Work Unit Evidence (Unit 2 — preserved from prior batch)

### Unit 2 first slice (Runtime)
- `uv run pytest tests/test_unit_2.py -q` → `6 passed`
- `uv run pytest -q` → `17 passed` (11 from Unit 1 + 6 from Unit 2 first slice)
- `uv run pytest -q --cov=llmux --cov-fail-under=90` → `17 passed`, 98%
- `uv run ruff check .` → `All checks passed!`
- `uv run mypy src tests` → `Success: no issues found in 7 source files`

### Unit 2 second slice (API)
- `uv run pytest tests/test_unit_2.py -q` → `16 passed`
- `uv run pytest -q` → `27 passed` (11 Unit 1 + 16 Unit 2)
- `uv run pytest -q --cov=llmux --cov-fail-under=90` → `27 passed`, 98%
- `uv run ruff format . && ruff check .` → `All checks passed`
- `uv run mypy src tests` → `Success: 14 source files`
- `uv run uvicorn llmux.main:app` → `/v1/health` 200, `/v1/models` 200, `/v1/chat/completions` 501 (identical both stream modes)

### Rollback (Unit 2)
First slice: drop `src/llmux/config.py`, `src/llmux/observability/`, `tests/test_unit_2.py` — restores to end-of-Unit-1 state. None imported from Unit 1's source.
Second slice: drop `src/llmux/main.py`, `src/llmux/api/`, `tests/conftest.py`; revert `tests/test_unit_2.py` to runtime-only parent (101-line version). `src/llmux/config.py` and `src/llmux/observability/` preserved.

## Restore Instructions (Child Slice)

---

## API Slice (restored onto runtime foundation)

### Status

**19/19 tasks complete** in the full merge (Phases 1–2 prior, Phase 3 runtime, Phase 4–5 API slice). Parent retains `config.py` and `observability/tracing.py` — not reintroduced.

### API Files Applied

| File | Lines | What |
|------|-------|------|
| `src/llmux/api/chat.py` | 38 | `POST /v1/chat/completions` 501 stub, `ChatMessage`/`ChatCompletionRequest`, single code path, no-fake-SSE |
| `src/llmux/api/health.py` | 17 | `GET /v1/health` gateway-native: `status`/`version`/`providers_configured` from `app.state.settings` |
| `src/llmux/api/models.py` | 12 | `GET /v1/models` OpenAI `{object:"list", data:[]}` |
| `src/llmux/main.py` | 34 | `create_app(settings)` factory: resolve Settings → store on state → mount `/v1/*` → wire OTel lifespan → export `app` |
| `tests/conftest.py` | 31 | `app` fixture + `client` fixture (TestClient) |
| `tests/test_unit_2.py` | 188 | Merged: **16 tests** (3 Settings + 3 Tracing + 2 health + 1 models + 1×3 chat + 3 app factory + 1 conftest) |

### Verification

| Check | Result |
|-------|--------|
| `uv run pytest tests/test_unit_2.py -q` | 16 passed |
| `uv run pytest -q` | 27 passed (11 Unit 1 + 16 Unit 2) |
| `uv run pytest -q --cov=llmux --cov-fail-under=90` | 27 passed, 98% |
| `uv run ruff format . && ruff check .` | All checks passed |
| `uv run mypy src tests` | Success: 14 source files |
| `uv run uvicorn llmux.main:app` | `/v1/health` 200, `/v1/models` 200, `/v1/chat/completions` 501 (identical both stream modes) |

### Rollback (candidate only)

Drop `src/llmux/main.py`, `src/llmux/api/`, `tests/conftest.py`; revert `tests/test_unit_2.py` to runtime-only parent (101-line version). `src/llmux/config.py` and `src/llmux/observability/` are preserved — they belong to the parent runtime slice, not the candidate.

### Delta vs `origin/feat/core-gateway-mvp`
| Source | + | − | Δ |
|--------|---|---|---|
| `apply-progress.md` (this section) | 0 | 0 | 0 |
| `tasks.md` | 8 | 8 | 16 |
| `test_unit_2.py` (101→188) | 91 | 4 | 95 |
| New API files (6) | 132 | 0 | 132 |
| **Total** | **231** | **12** | **243** |

## Remaining Tasks

None — all 26 tasks complete. Ready for `sdd-verify`, then `sdd-archive`.

## Deviations from Design

### Unit 2 (preserved)

1. **`Settings.llmux_providers_configured` needs `NoDecode`**: pydantic-settings 2.14 auto-decodes `list[str]` fields from JSON before the `field_validator(mode="before")` runs. Mitigated with `Annotated[list[str], NoDecode, Field(...)]`.
2. **No `__init__.py` files in `src/llmux/observability/`**: Python 3.12 namespace packages handle it.
3. **Test consolidation**: Tests in one file (`test_unit_2.py`) for line-budget efficiency.

### Unit 3 (this slice)

1. **Dockerfile is multi-stage and runs as non-root** — the proposal called for "minimal validated"; multi-stage is required to copy `uv` into the runtime image without bloating it. Still validates (`docker build` + `curl /v1/health` succeed).
2. **`hadolint` DL3008 warning** (apt versions not pinned) accepted: only `curl` and `ca-certificates`; pinning would create rebase noise for negligible benefit. No `hadolint` errors.
3. **Restore Notes** — this branch is a stacked child of `feat/core-gateway-mvp`; chain strategy is `stacked-to-main`. The PR diff stays focused on Phase 6 + 1.5. `apply-progress.md` was updated by appending Unit-3 evidence (prior 209-line content preserved).
