# THE PROFESSOR — Build Task Ledger

**Last reconciled:** 2026-11-22  
**Purpose:** Durable task state so work is never reported as merely planned when it is not executed.

## Status rules
- **NOT STARTED** — no execution evidence yet.
- **IN PROGRESS** — active work has begun; include the current action and last evidence.
- **BLOCKED** — a named dependency, approval, or technical issue prevents progress; include the unblock action.
- **DONE** — only when a concrete result is verified (commit/file, test result, or checked runtime behavior).
- **VERIFY** — work exists, but evidence is stale, incomplete, or not yet checked.

Every task must have an owner (Professor build engine), a status, evidence, and next action. Move tasks to DONE only after verification. Update this ledger at every task boundary and checkpoint.

## Current five-point build cycle

| ID | Task | Status | Evidence / current state | Next action |
|---|---|---|---|---|
| P1 | Reconcile baseline and dependency stack | IN PROGRESS | PR #1 is open/draft, exact head `f8d6eac412d1031430bee6b3740dc67113b854ec`; 50 files, 9,770 additions / 669 deletions; historical exact-head CI passed. PRs #46–#76 remain a large draft stack. | Refresh exact heads/CI, establish smallest safe merge/review order, identify blockers/duplicates. |
| P2 | Connect real Professor reasoning/chat path | NOT STARTED | PR #46–#48 exist; #48 prompt-budget changes; prior evidence says #66 chat delivery delta is already ported into #48. | Inspect composition and runtime path, tests, identify disconnected/missing piece. |
| P3 | Persistent, governed learning | NOT STARTED | Learning memory/evaluator/proposal code exists in PR #1; validation and integration are not proven end-to-end. | Inspect storage/retrieval and task lifecycle; design and implement evidence-backed learning integration on isolated branch. |
| P4 | Integration and security verification | NOT STARTED | Historical branch CI is not deployment/runtime proof. | Build test matrix and run exact-head checks for core path, identity, tenancy, storage, cancellation, recovery, learning. |
| P5 | Live end-to-end readiness | NOT STARTED | No current verified live deployment/runtime proof in this checkpoint. | Determine free-host/local startup path; test on a safe environment; deployment remains approval-gated. |

## Active task
**P1 — baseline and dependency reconciliation.** Work remains IN PROGRESS until the current PR stack and CI are refreshed and a focused, evidence-based order/blocker list is produced.

## Working protocol
1. Select one task; record it as **IN PROGRESS** with task ID and intended result.
2. Execute concrete work (code, tests, inspection, or document).
3. Verify result using exact evidence: commit SHA, file path, test command/results, CI run/head, or runtime observation.
4. Mark **DONE** only when verification passes; otherwise mark **BLOCKED** or **VERIFY** and state the reason.
5. Update this ledger and the checkpoint before switching tasks.
6. Start the next task immediately when safe; do not wait for user input for routine read-only or isolated-branch work.

## Safety / scope
- GitHub/free tools first; avoid Replit unless an emergency.
- No unnecessary credits, paid services, or automated watches.
- Do not merge, deploy, transfer source, modify production, run production migrations, expose secrets, enable payments, or activate external write integrations without separate explicit approval.
- No speculative completion claims. CI success is not deployment proof.

## Checkpoint log
### 2026-11-22 — tracking system established
- Confirmed open PR inventory through GitHub; current draft stack includes PRs #1 and #46–#76.
- PR #1 exact head remains the baseline repair head recorded above; it is open, draft, mergeable, not merged.
- PR #48 is open/draft and its head is `2f0e678a2a403502bce712d34d8e7917a01edf10`.
- This ledger is being added on an isolated branch from PR #1's exact head; it does not modify `main`, merge, or deploy.
- **Next:** refresh the dependency PR heads and CI; review the baseline repair and decide the narrowest next engineering action.

