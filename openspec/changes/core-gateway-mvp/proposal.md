# Proposal: Core Gateway MVP — first vertical slice

> **Change**: `core-gateway-mvp`  ·  **Issue**: `Closes #3` (`status:approved`)  ·  `Related to #1`
> **Branch**: `feat/core-gateway-mvp` (base: `docs/foundation`)  ·  **Mode**: `auto`  ·  **Store**: `openspec`
> **Review budget**: ≤ 400 authored changed lines  ·  **Status**: Proposed

## Intent

Turn the docs-only `llmux` repo into a runnable, reviewable backend by landing the **first vertical slice**: real Python tooling, strict-TDD capability, an OpenAI-compatible API boundary, and the ports/adapters skeleton from ADR-0001 / ADR-0002. This slice closes **issue #3 only** — it is explicitly **not** ROADMAP Phase 1 (see Acceptance Boundary).

## Scope

### In Scope
- **`uv` tooling**: `pyproject.toml` (FastAPI, Pydantic v2, OTel api+sdk, httpx, pytest, pytest-asyncio, ruff, mypy) + committed `uv.lock`; `ruff.toml`.
- **Runtime skeleton** (package `llmux`): `main.py` app factory, `config.py` (Pydantic v2 `Settings`), `observability/tracing.py` (OTel tracer boundary, no-op unless endpoint set).
- **API boundary** under `/v1`:
  - `GET /v1/health` → 200 `{status, version, providers_configured}` — **gateway-native** (OpenAI has none).
  - `GET /v1/models` → 200 empty list — **OpenAI-compatible**.
  - `POST /v1/chat/completions` → **501** OpenAI-shaped error for **both** `stream=true` and `stream=false`. **No fake SSE.**
- **Ports/adapters skeleton**: `core/providers/base.py` — `ProviderAdapter` Protocol + `CompletionResult` / `Chunk` / `ModelInfo` / `HealthStatus` per ADR-0002 (**planned**; no concrete adapter).
- **Strict-TDD plumbing**: `conftest.py`, tests per endpoint + protocol, `.github/workflows/ci.yml` (`uv run ruff check .` → `uv run pytest -q`).
- **Docs/contract deltas**: `.env.example`, `Dockerfile` (if budget), `CONTRIBUTING.md` setup block, `openspec/config.yaml` flips (`strict_tdd: true`, `detected_runner: pytest`, `test_command`, `coverage_threshold: 90`), ADR-0001/0002 `Proposed → Accepted`.

### Non-Goals (explicit)
- No real OpenAI/Anthropic provider; no API-key auth; no PostgreSQL/Redis/Alembic.
- No real streaming (`complete_stream` declared, unimplemented).
- No router, fallback, metering, cost, rate-limiting, audit log, admin API/dashboard, Docker Compose, architecture-fitness tests.
- Chat does **not** emit fake SSE — both stream modes return the identical 501 contract.
- Does **not** close ROADMAP Phase 1, issue #1, or any downstream slice (forecast: exploration §6).

## Capabilities

> Contract for `sdd-spec`. `openspec/specs/` is empty (greenfield) → all new, none modified.

### New Capabilities
- `gateway-api-boundary`: gateway-native `/v1/health` + OpenAI-compatible `/v1/models` and `/v1/chat/completions` (501 for both stream modes).
- `provider-abstraction`: `ProviderAdapter` Protocol + dataclasses per ADR-0002 (**planned** — concrete adapters deferred).

### Modified Capabilities
- None.

## Approach

Greenfield single PR. Docs already settle FastAPI, Pydantic v2, Python 3.12+, pytest, modular monolith w/ ports/adapters (ADR-0001) — not relitigated. Dependency manager = **`uv`** (matches user tooling; single `uv.lock` = CI contract; mental model: `uv sync` / `uv run pytest` / `uv run uvicorn llmux.main:app`). Architectural choices cite **ADR-0001** (topology, `core/providers/base.py`) and **ADR-0002** (adapter surface `complete` / `complete_stream` / `models` / `health`). Strict TDD is phrased as **"capability established"** — first true TDD consumer is the provider slice. Per config rule, all provider-abstraction wording is marked `(planned)`; no code is assumed unwritten.

### Assumptions preserved (auto-mode, from exploration §7.3)
1. Package name = `llmux` (imports `llmux.core.providers.base`).
2. Tooling = `uv` (lockfile committed).
3. Health is **gateway-native**; `/v1/models` + `/v1/chat/completions` are **OpenAI-compatible**.
4. Both chat stream modes return the **same 501 contract** — no fake SSE.
5. Issue #3 (already `status:approved`) is the closure target; `Related to #1` for partial foundation remediation only.

## Affected Areas

| Area | Impact | Change |
|------|--------|--------|
| `pyproject.toml`, `uv.lock`, `ruff.toml`, `.env.example`, `Dockerfile` | New | Backend tooling + container boundary |
| `src/llmux/{main,config}.py`, `api/{health,chat,models}.py`, `core/providers/base.py`, `observability/tracing.py` | New | Runtime + API + ports skeleton |
| `tests/{conftest.py,api/*,core/*}` | New | Strict-TDD proof |
| `.github/workflows/ci.yml` | New | CI runs `ruff` + `pytest` |
| `CONTRIBUTING.md`, `openspec/config.yaml`, `docs/adr/000{1,2}-*.md` | Modified | Activate setup, flip TDD config, ADRs → Accepted |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| 400-line budget pressure (~370 forecast) | Medium | Drop `Dockerfile` first (MEDIUM, not BLOCKER), then ADR status flips, then `pytest.ini` block |
| ADRs marked Proposed while code now reflects them | Medium | Flip `Proposed → Accepted` in this slice (2 lines × 2) |
| PR #2 (`docs/foundation`) still open; reviewers see partial issue-#1 remediation | Low | Call out in PR description; link `Related to #1`, not `Closes #1` |
| Strict TDD flipped on with only a 501 stub to test | Low | Phrase as "TDD capability established"; provider slice is first real consumer |
| `uv.lock` unfamiliar to first-time reviewers | Low | CONTRIBUTING.md names the 3 commands |

## Rollback Plan

Greenfield slice — no existing production code is modified. Rollback = **revert the merge commit** + delete `feat/core-gateway-mvp`. All changes are additive (new files) or docs/config deltas that revert cleanly:
- `openspec/config.yaml` flips revert to `strict_tdd: false`, `detected_runner: none`.
- ADR status flips revert to `Proposed`.
- `.env.example` / `Dockerfile` removal also reverts the partial issue-#1 remediation — re-open those findings if rolled back.

No data, migrations, or persisted state to recover.

## Dependencies

- Base branch: `docs/foundation` (orchestrator choice; PR #2 blocked on external approval). Not rebased onto `main`.
- Issue #3 (`status:approved`) — approved implementation target.
- External: PyPI, pinned in committed `uv.lock` for reproducibility.

## Issue Linkage

- `Closes #3` — *feat(backend): scaffold FastAPI and gateway API boundaries* (approved).
- `Related to #1` — partial foundation remediation (`.env.example` + `Dockerfile` findings only; remaining blockers deferred to later slices).

## Success Criteria

- [ ] `GET /v1/health` → 200 `{status, version, providers_configured}`.
- [ ] `GET /v1/models` → 200 empty list.
- [ ] `POST /v1/chat/completions` → 501 (OpenAI error envelope) for **both** stream modes — no fake SSE.
- [ ] `uv sync --frozen` installs; `uv run pytest -q` green in CI; `uv run ruff check .` passes.
- [ ] `ProviderAdapter` Protocol + dataclasses import; Protocol subclassable.
- [ ] PR diff ≤ 400 authored lines (no `size:exception`).

## Acceptance Boundary

This slice closes **issue #3 only**. It does **not** close ROADMAP Phase 1, issue #1, or any downstream slice. The 501 chat response and empty `/v1/models` are **contract-correct stubs**, not features — provider implementation, persistence, auth, streaming, metering, and admin surface remain out of scope (exploration §6 forecast).
