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
| P1 | Reconcile baseline and dependency stack | IN PROGRESS | Exact-head inventory refreshed 2026-11-22: #1/#46-#49/#57/#62-#65/#75/#76 are open draft PRs; all recorded heads match prior checkpoint; exact-head CI rechecked and success confirmed for #1, #48, #64, #76. | Finish focused security/core review and establish dependency/merge order. |
| P2 | Connect real Professor reasoning/chat path | NOT STARTED | PR #46–#48 exist; #48 prompt-budget changes; prior evidence says #66 chat delivery delta is already ported into #48. | Inspect composition and runtime path, tests, identify disconnected/missing piece. |
| P3 | Persistent, governed learning | NOT STARTED | Learning memory/evaluator/proposal code exists in PR #1; validation and integration are not proven end-to-end. | Inspect storage/retrieval and task lifecycle; design and implement evidence-backed learning integration on isolated branch. |
| P4 | Integration and security verification | NOT STARTED | Historical branch CI is not deployment/runtime proof. | Build test matrix and run exact-head checks for core path, identity, tenancy, storage, cancellation, recovery, learning. |
| P5 | Live end-to-end readiness | NOT STARTED | No current verified live deployment/runtime proof in this checkpoint. | Determine free-host/local startup path; test on a safe environment; deployment remains approval-gated. |

## Active task
**P3 — persistent, governed learning integration.** P3.1 architecture audit DONE; P3 remains IN PROGRESS because branch integration and live end-to-end evidence are absent. Next verify learning tests and map the task/evaluation → candidate lesson → human review → approved memory → retrieval cycle.

### Subtask states
- **P1.1 — Refresh current PR heads and exact-head CI evidence: DONE.** Confirmed #1, #48, #64, #76 exact heads; each associated core-test workflow completed successfully. PR metadata refreshed for #46-#49, #57, #62-#65, #75, #76. No merge or deployment performed.
- **P1.2 — Focused security/core review: IN PROGRESS.** Initial inspection confirms auth defaults to required in config, local executor is arithmetic-only, learning lessons cannot self-validate. Continue endpoint/storage review and identify concrete gaps.

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
- **Completed this checkpoint:** PR inventory refresh and exact-head CI verification (P1.1).
- **Current action:** focused review of baseline auth/storage/executor/learning boundaries (P1.2).
- **Next:** complete the dependency order/blocker map, then proceed to P2 reasoning/chat integration.


### 2026-11-22 — checkpoint update
- Verified exact-head workflow success: PR #1 `f8d6eac...` run 43489002177; PR #48 `2f0e678...` run 44475448752; PR #64 `7aa6e9b...` run 44178610630; PR #76 `40c4395...` run 44390312814.
- Refreshed metadata for PR #46, #47, #48, #49, #57, #62, #63, #64, #65, #75 and #76; all remain open/draft/unmerged and mergeable at the time checked.
- Initial source review: auth default is required (`ATLAS_API_REQUIRE_AUTH=true`); executor only permits bounded basic arithmetic; lesson creation enforces unvalidated status.
- **P1.1 marked DONE**; P1.2 remains IN PROGRESS.

### 2026-11-22 — focused review checkpoint
- **P1.2 marked DONE:** inspected app routes, auth/config, task intake/manager, local executor, learning memory, proposal review, and recovery storage.
- Findings confirmed: shared API-key authentication is not verified identity/RBAC/tenant isolation; caller-provided actor labels are audit metadata; arithmetic-only executor; no proposal test runner; learning is review-gated; SQLite is single-host. These are known readiness limits.
- **P1.3 — dependency order/blocker map: IN PROGRESS.** Next task is to consolidate the dependency graph and prioritize Professor-core PRs over unrelated market-intelligence feature branches.

### 2026-11-22 — dependency map checkpoint
- **P1.3 marked DONE:** dependency priority map recorded: baseline #1 → chat #46/#47/#48/#49 → identity/reasoning #10/#11 → OIDC #49–#57/#63 → worker safety #58–#64; source reconciliation #65 remains separate; market PRs #70–#76 deferred; #66 is duplicate/ported.
- **P1 completed:** inventory, review, and dependency reconciliation. No merge/deployment permission exercised.
- **P2 marked IN PROGRESS:** reasoning/chat path audit.

### 2026-11-22 — reasoning/chat audit checkpoint
- **P2 audit subtask DONE:** PR #11's app lifespan loads an explicitly configured OpenAI-compatible provider and injects it into ConversationService; provider config is opt-in, with fail-closed disabled behavior if configuration is invalid. Health/readiness explicitly reports live-provider round-trip as unverified.
- PR #11 exact-head CI run 43733864615 passed. PR #48 exact-head CI run 44475448752 passed.
- PR #46 adds integration tests; #47 requires explicit chat capability; #48 bounds evidence/memory and preserves task instructions within prompt budgets. The code is distributed across draft PR dependency stacks; no actual deployed conversation/provider round-trip is verified.
- **P2 remains IN PROGRESS** until dependency-stack integration and live/tested connection are verified. P3 learning audit now IN PROGRESS.

### 2026-11-22 — learning architecture audit checkpoint
- **P3.1 marked DONE:** PR #11 contains tenant/owner-scoped memory proposals, explicit approval/rejection, expiry-aware bounded retrieval, tenant isolation, and approved-memory retrieval wired into the authenticated conversation endpoint. Lesson review candidates are linked to evaluation IDs, immutable, tenant-scoped, and require explicit decision; runtime promotion is disabled.
- This is governed memory/lesson review, not proof of autonomous self-improvement. Automatic task outcome generation into candidate lessons and live end-to-end learning behavior remain unverified.
- **P3.2 IN PROGRESS:** test coverage and lifecycle verification.
