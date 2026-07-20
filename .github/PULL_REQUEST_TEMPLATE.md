<!-- ⚠️ READ BEFORE SUBMITTING
  Before opening: (a) `Closes #N` must reference an issue with `status:approved`,
  (b) apply exactly one `type:*` label, (c) PRs over 400 lines need `size:exception`.
  Missing a linked approved issue → rejected by CI.
  See the issue templates and PR checks for the contribution workflow.
-->

## 🔗 Linked Issue

<!-- Tracker or default-branch PR -->
Closes #

<!-- Child PR in feature-branch-chain -->
Related to #

<!-- Use EXACTLY ONE:
  - Tracker / default-branch PR: Closes #42
  - Child PR in feature-branch-chain: Related to #42
-->

---

## 🏷️ PR Type

What kind of change does this PR introduce?

- [ ] `type:bug` — Bug fix (non-breaking change that fixes an issue)
- [ ] `type:feature` — New feature (non-breaking change that adds functionality)
- [ ] `type:docs` — Documentation only
- [ ] `type:refactor` — Code refactoring (no functional changes)
- [ ] `type:chore` — Build, CI, or tooling changes
- [ ] `type:breaking-change` — Breaking change (fix or feature that changes existing behavior)

---

## 📝 Summary

<!-- Provide a clear and concise description of what this PR does and why. -->

---

## 📂 Changes

| File / Area | What Changed |
|-------------|-------------|
| `path/to/file` | Brief description |

---

## Chain Context

<!-- Fill ONLY if this PR is part of a chain.
  IMPORTANT:
  - Keep this heading EXACTLY as `## Chain Context` (no emoji/prefix changes), CI parses it literally.
  - Tracker PRs target `main` and use `Position | tracker`.
  - Child PRs target the tracker branch or the immediate parent branch, never `main`.
  - Child PRs use `Position | N of total`.
  - Tracker PRs must keep the Chain Status table below and list every child PR in the chain.
-->

| Field | Value |
|-------|-------|
| Chain | |
| Tracker PR | |
| Position | |
| Base | |
| Depends on | |
| Follow-up | |
| Review budget | / 400 |
| Starts at | |
| Ends with | |

### Chain Overview

```text
📍 This PR
```

### Chain Status

| PR | Scope | Status |
|----|-------|--------|
| #<!-- PR number --> | | 🟡 Open |

---

## 🧪 Test Plan

<!-- Describe how you tested this change. Include commands to run. -->

- [ ] Manually reviewed for accuracy
- [ ] Verified links and references

---

## 🤖 Automated Checks

| Check | Status | Description |
|-------|--------|-------------|
| Check Issue Reference | ⏳ | Tracker/default PR: `Closes/Fixes/Resolves #N`; child PR: `Related to #N` |
| Check Issue Has `status:approved` | ⏳ | Linked issue must have been approved before work began |
| Check PR Has `type:*` Label | ⏳ | Exactly one `type:*` label must be applied |
| Check PR Cognitive Load | ⏳ | PR should stay within 400 changed lines or use `size:exception` |

---

## ✅ Contributor Checklist

- [ ] PR is linked to an issue with `status:approved`
- [ ] Tracker/default PR uses `Closes #N`, child PR uses `Related to #N`
- [ ] If chained, this PR targets tracker/parent branch, not `main`
- [ ] I have added the appropriate `type:*` label to this PR
- [ ] PRs exceeding 400 changed lines include the `size:exception` label
- [ ] Changes reviewed for accuracy and completeness
- [ ] I have updated documentation if necessary
- [ ] My commits follow [Conventional Commits](https://www.conventionalcommits.org/) format
- [ ] My commits do not include `Co-Authored-By` trailers

---

## 💬 Notes for Reviewers

<!-- Optional: anything you want reviewers to pay special attention to. -->
