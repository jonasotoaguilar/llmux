# Contributing

Thanks for your interest in LLMux. This document outlines the contribution workflow, code standards, and review process.

## Quick Path

1. Find or create an issue with `status:approved`.
2. Create a branch.
3. Implement with conventional commits.
4. Open a pull request.
5. Wait for review and CI.

## Development Setup

The backend uses `uv` to manage Python 3.12+ dependencies and runtime. Three commands cover the core loop:

```bash
# 1. Install dependencies (uses committed uv.lock for reproducible installs)
uv sync --frozen --all-groups

# 2. Run the test suite (pytest with 90% coverage gate)
uv run pytest -q --cov=llmux --cov-fail-under=90

# 3. Launch the gateway locally (defaults: 0.0.0.0:8000)
uv run uvicorn llmux.main:app --reload
```

Backend stack: Python 3.12+, FastAPI, Pydantic v2, OpenTelemetry. Lint with `uv run ruff check .`, format with `uv run ruff format .`, type-check with `uv run mypy src tests`.

Dashboard and persistence layers (Next.js, PostgreSQL, Redis) are not in this slice — see ROADMAP.md for follow-up work.

## Branch Naming

Branches must follow `type/description`:

- `feat/provider-anthropic` — new feature
- `fix/rate-limit-race-condition` — bug fix
- `docs/architecture-update` — documentation
- `refactor/port-adapter-pattern` — code refactoring
- `chore/update-deps` — maintenance/tooling

## Conventional Commits

```text
feat(adapter): add Anthropic provider support
fix(metering): correct token counting for streaming responses
docs(arch): update NFR targets after benchmark
chore(deps): bump fastapi to 0.110.0
```

## Pull Request Process

1. Every PR must link an issue with `status:approved`.
2. PRs must stay within 400 changed lines or get a `size:exception` label.
3. All automated checks must pass.
4. At least one maintainer review is required before merge.
5. Squash merge into main.

### Automated Checks

| Check | What it validates |
|-------|------------------|
| Check Issue Reference | PR body contains `Closes/Fixes/Resolves #N` (tracker) or `Related to #N` (child PR) |
| Check Issue Approved | Linked issue has the `status:approved` label |
| Check PR Label | PR has exactly one `type:*` label |
| Check Cognitive Load | Total changed lines ≤ 400, or `size:exception` label present |

## Code Standards

### Backend (Python)

- Type hints required for all public functions and classes
- Async where I/O is involved
- Tests with pytest
- Format with ruff
- Import order: standard library → third-party → local (alphabetical within groups)

### Dashboard (TypeScript/React)

- TypeScript strict mode
- Server components by default, client components only when interactivity requires them
- Tailwind CSS for styling — no CSS modules or styled-components
- React Server Actions for mutations
- Tests with bun:test + React Testing Library

### General

- No `Co-Authored-By` or AI attribution in commits
- Documentation in English
- Update relevant docs (README, ARCHITECTURE, DESIGN) when behavior changes

## Issue Tracking

- Bug reports and feature requests use GitHub Issues
- Questions go to Discussions
- Every issue automatically gets `status:needs-review` — a maintainer must add `status:approved` before work begins

## Security

See [SECURITY.md](./SECURITY.md) for the security policy and vulnerability reporting.
