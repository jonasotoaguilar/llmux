# Tasks: Core Gateway MVP

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated authored lines | ~380 (tooling 65, source 155, tests 110, CI/docs 50) |
| Generated in snapshot, **excluded** from authored count | `uv.lock` (generated, snapshot identity only) |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR #1 → PR #2 → PR #3, stacked-to-main |
| Delivery strategy | auto-forecast |
| Chain strategy | stacked-to-main (auto-forecast resolves on forecast) |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Tooling + provider port (TDD loop established) | PR #1 → main | `uv run pytest tests/core -q` green, ≥5 tests | `uv run pytest -q` exit 0 | Drop `pyproject.toml`, `uv.lock`, `ruff.toml`, `.env.example`, `src/llmux/__init__.py`, `src/llmux/core/__init__.py`, `src/llmux/core/providers/__init__.py`, `src/llmux/core/providers/base.py`, `tests/core/*` (no `tests/conftest.py` — Unit 2/app factory) |
| 2 | API routes + factory + observability | PR #2 → main | `uv run pytest -q --cov=llmux --cov-fail-under=90` green, ≥11 tests | `uv run uvicorn llmux.main:app` + `curl -i :8000/v1/health` → 200 JSON | Drop `src/llmux/{main,config}.py`, `src/llmux/api/*`, `src/llmux/observability/tracing.py`, `tests/api/*` |
| 3 | CI + config/ADR/docs deltas | PR #3 → main | `ruff check . && mypy src && pytest -q` green locally | Push branch → `.github/workflows/ci.yml` green | Drop `.github/workflows/ci.yml`, `openspec/config.yaml` flips, ADR-0001/0002 status lines, `CONTRIBUTING.md` setup block, exploration §6 note |

> First apply batch (PR #1) is viable standalone: bootstraps `uv run pytest`, exercises strict TDD, ships no fake Phase-1 closure.

## Phase 1: Tooling Foundation (pre-TDD — no test runner yet)

- [x] 1.1 Create `pyproject.toml`: package `llmux`, src layout, runtime = FastAPI/Uvicorn/pydantic-settings/OTel API+SDK/OTLP HTTP; dev = httpx/pytest/pytest-asyncio/pytest-cov/Ruff/mypy; `[tool.pytest.ini_options]`
- [x] 1.2 Generate `uv.lock` via `uv lock` (committed; **excluded** from authored count)
- [x] 1.3 Create `ruff.toml` (line-length, target py312, isort groups)
- [x] 1.4 Create `.env.example` listing `LLMUX_HOST`/`PORT`/`VERSION`/`PROVIDERS_CONFIGURED`/`OTEL_SERVICE_NAME`/`OTEL_EXPORTER_OTLP_ENDPOINT`
- [ ] 1.5 *(droppable on >400-line pressure)* `Dockerfile` (python:3.12-slim, `uv sync --frozen`, uvicorn entrypoint)

## Phase 2: Provider Port (strict TDD — first RED→GREEN→REFACTOR)

Each row: RED failing test → GREEN production code → REFACTOR clean typing.

- [x] 2.1 TDD row — `ProviderAdapter` Protocol: RED imports + subclasses + 4 members → GREEN Protocol in `src/llmux/core/providers/base.py` → REFACTOR inputs as `Sequence[Mapping[str, object]]`/`Mapping[str, object]`
- [x] 2.2 TDD row — `CompletionResult` (`frozen, slots`, `raw=<empty-mapping factory>`): RED construct/read → GREEN dataclass → REFACTOR
- [x] 2.3 TDD row — `Chunk` (`finish_reason=None`): RED construct/read → GREEN dataclass → REFACTOR
- [x] 2.4 TDD row — `ModelInfo` (`supports_streaming`): RED construct/read → GREEN dataclass → REFACTOR
- [x] 2.5 TDD row — `HealthStatus` (`latency_ms=None, error=None`): RED construct/read → GREEN dataclass → REFACTOR
- [x] 2.6 TDD row — `complete_stream` typing: RED asserts sync method returning `AsyncIterator[Chunk]` (no nested coroutine) → GREEN declaration → REFACTOR

## Phase 3: Settings + Observability

- [ ] 3.1 TDD row — `Settings` (Pydantic v2 `BaseSettings`): RED maps envs to host/port/version/providers_configured/otel → GREEN `src/llmux/config.py` → REFACTOR
- [ ] 3.2 TDD row — `tracing.build_tracer`: RED no exporter when endpoint unset; SDK provider built when set → GREEN `src/llmux/observability/tracing.py` no-op default + OTLP/HTTP + batch processor (no credential/request capture) → REFACTOR

## Phase 4: API Routes (strict TDD)

- [ ] 4.1 TDD row — `GET /v1/health`: RED 200 + exact `{status, version, providers_configured}` JSON, gateway-native (not OpenAI) → GREEN `src/llmux/api/health.py` → REFACTOR
- [ ] 4.2 TDD row — `GET /v1/models`: RED 200 + `{object:"list", data:[]}` envelope → GREEN `src/llmux/api/models.py` static list → REFACTOR
- [ ] 4.3 TDD row — `POST /v1/chat/completions` 501 (stream=false): RED 501 + OpenAI error envelope + `application/json` (not `text/event-stream`) → GREEN `src/llmux/api/chat.py` + `ChatMessage`/`ChatCompletionRequest`/`OpenAIError`/`ErrorDetail` Pydantic models → REFACTOR
- [ ] 4.4 TDD row — chat 501 identical for `stream=true` and `stream`-omitted: RED all three stream cases produce identical body, content-type, no `data:` SSE → GREEN confirm single code path → REFACTOR

## Phase 5: App Factory + Test Harness

- [ ] 5.1 TDD row — `create_app` + `app` export: RED all three `/v1` paths reachable via TestClient + OTel lifespan shutdown hook fires → GREEN `src/llmux/main.py` resolves Settings → stores on `app.state` → mounts `/v1` → wires tracing lifespan → exports `app = create_app()` → REFACTOR
- [ ] 5.2 Create `tests/conftest.py` with `client` fixture (FastAPI TestClient) and ASGI-boundary helpers

## Phase 6: CI + Config/ADR/Docs Deltas

- [ ] 6.1 Create `.github/workflows/ci.yml`: `uv sync --frozen` → `ruff check .` → `mypy src` → `pytest -q --cov=llmux --cov-fail-under=90`
- [ ] 6.2 Flip `openspec/config.yaml` (`strict_tdd: true`, `detected_runner: pytest`, `test_command`, `coverage_threshold: 90`); update `context:` block
- [ ] 6.3 Flip ADR-0001 status: `Proposed` → `Accepted`
- [ ] 6.4 Flip ADR-0002 status: `Proposed` → `Accepted`
- [ ] 6.5 Append `CONTRIBUTING.md` Development Setup block (3 commands: `uv sync` / `uv run pytest` / `uv run uvicorn llmux.main:app`)
- [ ] 6.6 Append §6 forecast note to `openspec/changes/core-gateway-mvp/exploration.md`: 501 chat + empty `/v1/models` are contract-correct stubs, not Phase-1 closure (cross-ref proposal Acceptance Boundary)
