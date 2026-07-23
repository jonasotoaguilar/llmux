# Archive Report: core-gateway-mvp

**Change**: `core-gateway-mvp`
**Issue**: `Closes #3` (`status:approved`) · `Related to #1`
**Archive date**: 2026-07-23
**Archive path**: `openspec/changes/archive/2026-07-23-core-gateway-mvp/`
**Store / mode**: OpenSpec / repo-local
**Strict TDD**: Active
**Source revision at archive time**: `3897b0a` (`ci: activate core gateway delivery gates (#7)`)
**Review authority**: `allow` bound to `review-5dabb3531d6012a3`
**Status**: success — PASS WITH WARNINGS preserved as follow-up

---

## 1. Outcome

| Item | Value |
|---|---|
| Verdict | **pass with warnings** (0 CRITICAL, 0 blockers) |
| Requirements covered | 11 / 11 |
| Scenarios covered | 13 / 13 |
| Tasks completed | 25 / 25 (`tasks.md` — all `[x]`) |
| Test exit | 0 (27/27 collected, 97.78 % coverage, threshold 90 %) |
| Build/quality exit | 0 (`ruff check .` + `mypy src tests` clean) |
| Container runtime | PASS (`docker build` + `HEALTHCHECK` becomes healthy) |
| Specs synced to source of truth | 2 / 2 (`gateway-api-boundary`, `provider-abstraction`) |
| Change folder moved to archive | YES |
| Active `changes/` directory | empty for this change |

The SDD cycle is **complete** for `core-gateway-mvp`. No implementation edits, commits, pushes, or PRs were performed by this archive run.

---

## 2. Specs Synced

`openspec/specs/` was **empty** (greenfield). Both delta specs were promoted to source of truth via direct copy with a normalized `## Purpose` / `## Requirements` layout and an explicit cross-reference back to the archived delta.

| Domain | Action | Requirements | Scenarios | Source delta |
|---|---|---:|---:|---|
| `gateway-api-boundary` | Created | 5 ADDED | 7 scenarios | `archive/2026-07-23-core-gateway-mvp/specs/gateway-api-boundary/spec.md` |
| `provider-abstraction` | Created | 6 ADDED | 6 scenarios | `archive/2026-07-23-core-gateway-mvp/specs/provider-abstraction/spec.md` |
| **Total** | **2 created** | **11** | **13** | — |

No MODIFIED, REMOVED, or RENAMED sections were present in either delta; the merge pass was a straight copy, not a conflict resolution.

**`rules.archive` check**:
- `Warn before merging any delta marked (planned) that has not been implemented` — `provider-abstraction` carries `(planned)` markers on all six requirements. They are **not** unimplemented: per `verify-report.md` all six provider-abstraction scenarios pass (ProviderAdapter import/subclass, four dataclass constructibility, four Protocol members declared). `(planned)` here refers to "no concrete adapter exists", not to the contract surface being unimplemented. The contract surface (Protocol + dataclasses) IS implemented, tested, and shipped. **No archive hold.**
- `Preserve ADR cross-references in archived change folders` — `proposal.md` and `exploration.md` cross-reference `ADR-0001` (modular monolith topology) and `ADR-0002` (provider abstraction pattern). Both ADRs were flipped `Proposed → Accepted` in Phase 6.2/6.3. The archive folder preserves all references. **Pass.**

---

## 3. Archive Contents

```
openspec/changes/archive/2026-07-23-core-gateway-mvp/
├── apply-progress.md     14.8K  — Unit 1 + Unit 2 + Unit 3 evidence (243 lines)
├── design.md              6.4K  — Architecture decisions, interfaces, traceability
├── exploration.md        20.1K  — Pre-proposal research; §6 forecast note appended in 6.6
├── proposal.md            7.2K  — Intent, scope, capabilities, rollback, success criteria
├── specs/
│   ├── gateway-api-boundary/spec.md    4.0K  — 5 requirements, 7 scenarios
│   └── provider-abstraction/spec.md    3.8K  — 6 requirements, 6 scenarios
├── tasks.md               6.1K  — 25/25 tasks `[x]`; no stale checkboxes
└── verify-report.md      11.1K  — PASS, 11/11 requirements, 13/13 scenarios
```

| Artifact | Archived | Tasks complete |
|---|:-:|:-:|
| `proposal.md` | ✅ | n/a |
| `specs/` (both domains) | ✅ | n/a |
| `design.md` | ✅ | n/a |
| `tasks.md` | ✅ | 25 / 25 |
| `verify-report.md` | ✅ | n/a |
| `apply-progress.md` | ✅ | 25 / 25 (counted at row level; see §5) |
| `exploration.md` | ✅ | n/a |

---

## 4. Source of Truth Updated

The following specs now reflect the verified behavior of the shipped slice and serve as the source of truth for future changes:

- `openspec/specs/gateway-api-boundary/spec.md` — 5 requirements, 7 scenarios
- `openspec/specs/provider-abstraction/spec.md` — 6 requirements, 6 scenarios

Each main spec file was written with a `## Purpose` block, a `## Requirements` block (instead of `## ADDED Requirements` since these are no longer deltas), the original requirements/scenarios verbatim, and an explicit Source cross-reference back to the archived delta for traceability.

---

## 5. Discrepancies Observed (no operational impact)

These are recorded in `verify-report.md` as **WARNING** (non-behavioral, non-blocking) and are preserved here as follow-up. None of them changes the archive outcome.

1. **CI does not run `uv run ruff format --check .`.** Fresh local format check passed. Follow-up: add the format guard to `.github/workflows/ci.yml` to lock formatting in CI.
2. **ADR-0002 follow-up checklist items for the now-present `ProviderAdapter` and dataclasses remain unchecked.** ADR status is `Accepted`; spec coverage passes. Follow-up: tick the checklist items in `docs/adr/0002-provider-abstraction-pattern.md`.
3. **`apply-progress.md` reports `26/26` tasks but `tasks.md` has 25 rows.** No task is unchecked; the off-by-one is a documentation-count mismatch (Unit 1 + Unit 2 + Unit 3 narrative vs the 25-row `tasks.md`). Follow-up: reconcile the count wording in `apply-progress.md`.
4. **`apply-progress.md` duplicates preserved API-slice/restore evidence after the cumulative Unit-3 evidence.** Provenance noise, not contradictory evidence. Follow-up: trim the duplicated section when re-touching `apply-progress.md`.

These are all **housekeeping / documentation hygiene** items. They are explicitly out of scope for this archive and should be addressed in a follow-up change. No source code, test, or contract is affected.

---

## 6. Review Gate

| Field | Value |
|---|---|
| `reviewGate.result` | `allow` |
| `reviewGate.id` | `review-5dabb3531d6012a3` |
| Status match | Allow gate present; structured status reports `archive=ready`, `nextRecommended=archive`, `blockedReasons=[]` |
| Verdict | `pass` (no critical findings, no blockers) |

Archive proceeded because the review gate is `allow`, the verdict has zero CRITICAL findings, and every implementation task is complete in the persisted `tasks.md`.

---

## 7. SDD Cycle

| Phase | Status | Artifact |
|---|---|---|
| Propose | ✅ done | `proposal.md` |
| Spec | ✅ done | `specs/{gateway-api-boundary,provider-abstraction}/spec.md` |
| Design | ✅ done | `design.md` |
| Tasks | ✅ done | `tasks.md` (25/25) |
| Apply | ✅ done | `apply-progress.md` (Unit 1 + Unit 2 + Unit 3) |
| Verify | ✅ done | `verify-report.md` (PASS, 11/11, 13/13) |
| Archive | ✅ done | this file + moved change folder |

The change has been fully planned, implemented, verified, and archived. Ready for the next change.

---

## 8. Next Recommended

`none` — the SDD cycle for `core-gateway-mvp` is complete. The next change should be initiated by the orchestrator only when the follow-up items in §5 are scheduled or a new slice is approved (e.g. concrete provider adapter, persistence layer, streaming, metering, admin surface).
