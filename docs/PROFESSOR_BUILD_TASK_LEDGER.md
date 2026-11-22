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
| P1 | Reconcile baseline and dependency stack | DONE (audit only) | Inventory, security/core review, dependency map documented. PR #1 remains draft/unmerged. | Merge/review decisions are approval-gated. |
| P2 | Connect real Professor reasoning/chat path | DONE (branch integration/tests) | PR #48 contains PR #11 provider foundation in ancestry; combined chat/provider stack exact-head CI passed (929 tests). No live provider round-trip/deployment. | Live runtime verification remains P5. |
| P3 | Persistent, governed learning | DONE (branch implementation/tests) | PR #79 and #80 add explicit feedback candidate and two-step approval-to-memory proposal workflow. PR #80 exact-head CI: 786 passed. Not merged/deployed. | Live verification under P5. |
| P4 | Integration and security verification | DONE (branch integration CI) | PR #82's merge ref combines PR #64 worker/OIDC stack with PR #81 chat/provider/learning; CI run 45046895853 passed 1179 tests. Draft/unmerged. | Live runtime and deployment verification remains P5. |
| P5 | Live end-to-end readiness | BLOCKED | Release smoke checklist prepared. Current readiness code shows hosted-login services missing and live provider round-trip false. No deployment approval or live environment verified. | Obtain approval for a free safe test environment; then run the checklist. |

## Active task
**P5 — live end-to-end readiness.** P1–P4 are DONE at audit/branch-test level. PR #82 merge-ref CI passed 1179 tests. P5 is BLOCKED: no live deployment/provider round-trip is verified, hosted login services remain missing, and deployment remains approval-gated. P5.1 smoke checklist is DONE.

### Subtask states
- **P1.1 — PR inventory and exact-head CI refresh: DONE.**
- **P1.2 — focused core/security review: DONE.** Known limitations: shared API-key auth is not verified identity/RBAC/tenant isolation; actor labels are caller supplied; arithmetic-only executor; proposal testing not implemented; SQLite single host.
- **P1.3 — dependency map: DONE.** Priority chain: baseline #1 → chat #46/#47/#48/#49 → identity/reasoning #10/#11 → hosted OIDC #49–#57/#63 → worker safety #58–#64. Source reconciliation #65 separate; market PRs #70–#76 deferred; #66 duplicate/ported.
- **P2: DONE at branch/test level.** Compare confirms PR #11 is an ancestor of PR #48. PR #48 CI #44475448752 passed 929 tests; provider is opt-in. No live provider round-trip verified.
- **P3.1–P3.5: DONE at code/test level on stacked draft branches.** PR #79 exact-head CI #45046430157 success; PR #80 exact-head CI #45046596722 success (786 passed, 1 warning). Pending lesson and memory approvals are separate; no automatic promotion or self-modification.

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

### 2026-11-22 — learning coverage checkpoint
- **P3.2 marked DONE (audit):** PR #11 exact-head CI succeeded; memory tests explicitly cover approval-before-retrieval, owner/tenant isolation, scope enforcement, decision single-use, rejected-memory exclusion, input/retention bounds, and deletion. Lesson tests cover owned evaluation evidence, independent reviewer, immutable candidates/decisions, and runtime promotion disabled.
- Gap: lessons can be manually proposed against evaluations, but no verified automatic or deterministic task-outcome-to-candidate pipeline is present. Approved lesson candidates are not promoted into runtime memory; promotion is deliberately disabled. User-approved durable memory proposals are a separate mechanism and do feed approved memories into reasoning.
- **P3.3 IN PROGRESS:** define the safest controlled feedback loop and evidence required before implementation.

### 2026-11-22 — learning loop design checkpoint
- **P3.3 marked DONE:** safe workflow design documented. Candidate creation is deterministic from explicit user feedback, pending only, evidence-linked, bounded, and requires independent approval; no prompt/runtime promotion.
- **P3.4 DONE:** implementation on draft PR #79; exact-head workflow run 45046319590 completed successfully.

### 2026-11-22 — feedback-to-candidate implementation checkpoint
- Draft PR #79 adds deterministic pending lesson candidate creation from explicit negative/partial feedback, only when `lessons:propose` scope is present. Candidate text is bounded, linked to evaluation ID, pending, requires independent review, and runtime promotion is disabled.
- Tests added: negative feedback creates a pending candidate linked to the evaluation; positive feedback does not create one.
- Exact head: `afb962cbe8043cdf90c56417a69fb8195c31065c`. Workflow run 45046319590: dependency installation succeeded and test step completed successfully; overall job finalization was still in progress at checkpoint.
- **P3.4 VERIFY** until overall CI finishes.

### 2026-11-22 — P3.4 completion
- PR #79 exact head verified: `afb962cbe8043cdf90c56417a69fb8195c31065c`; draft, open, mergeable, unmerged.
- Workflow run 45046319590 completed with **success**. Test step passed; full job completed.
- **P3.4 marked DONE.** Negative/partial explicit feedback now creates a pending, bounded, evidence-linked lesson candidate only when the principal has `lessons:propose`; positive feedback creates none. No automatic approval or runtime promotion.
- **P3.5 VERIFY:** draft PR #80 implements a separate explicit owner action to convert an independently approved lesson into a pending memory proposal (never directly into approved memory); exact-head CI run 45046500790 was in progress.

### 2026-11-22 — start P3.5
- Task **IN PROGRESS**: explicit owner-controlled conversion of an independently reviewed approved lesson candidate into a pending memory proposal. This keeps two approval gates: lesson review and memory approval; no direct prompt promotion.

### 2026-11-22 — P3.5 implementation checkpoint
- PR #80 created on isolated branch `atlas/approved-lesson-memory-proposal-v1`, stacked on PR #79. It adds an owner-scoped method/API route, deterministic idempotency key, bounded copy into pending memory, and tests for second approval, repeat requests, pending rejection, and cross-owner denial.
- Exact head: `21fb41630b21d0d09594da53b9d763414c1bb619`. Initial CI exposed the new verified-identity route missing from the security-route allowlist (785 passed, 1 failed). The allowlist was corrected in commit `2798b198934cb51fe6a80ededcdf673caad31e02`; new exact-head workflow run 45046596722 is in progress. **P3.5 VERIFY** until completed.

### 2026-11-22 — CI defect and correction
- PR #80 first full test run failed only because the security audit allowlist did not include the new verified-identity route. Log evidence: 785 passed, 1 failed (`test_every_private_api_route_declares_the_api_key_dependency`).
- Added the new route to the verified-identity route set in `tests/test_security.py`; latest head is `2798b198934cb51fe6a80ededcdf673caad31e02`. Workflow run 45046596722 is pending.

### 2026-11-22 — P3 governed learning completion
- PR #80 exact head `2798b198934cb51fe6a80ededcdf673caad31e02` verified by workflow run 45046596722: **786 passed, 1 warning in 16.21s**; conclusion success.
- Failure found during this cycle was the route-security allowlist missing the new identity-protected endpoint; corrected and exact-head CI passed.
- P3.5 marked DONE. Combined branch stack implements explicit negative-feedback candidate capture, independent lesson review, owner-controlled conversion to pending memory, second memory approval before retrieval, idempotency, and owner isolation.
- **P3 marked DONE at code/test level**; this is not a merge or deployment claim. P4 integration/security verification is now IN PROGRESS.

### 2026-11-22 — P4.1 CI evidence matrix
- **P4.1 DONE:** added `docs/PROFESSOR_TEST_EVIDENCE_MATRIX_2026-11-22.md` with exact-head results for PRs #1, #11, #46–#49, #62–#64, #76, #79 and #80. All recorded workflows succeeded; the matrix distinguishes CI from integration/runtime proof.
- Verified test counts from logs: #1 237; #46 925; #47 926; #48 929; #49 929; #11 781; #62 1151; #63 1101; #64 1174; #76 289; #79 783; #80 786. One non-blocking deprecation warning on each run.
- **P4.2 IN PROGRESS:** cross-stack integration and security dependency review.

### 2026-11-22 — P4.2 combined chat/provider/learning verification
- Compare confirmed PR #11 reasoning-provider branch is an ancestor of PR #48 prompt-budget/chat branch. This corrects the earlier assumption that these stacks were fully separate.
- Draft integration PR #81 targets PR #48 with PR #80 learning changes. Its pull_request workflow run 45046596722 completed successfully: **786 passed, 1 warning**. The run metadata confirms base SHA `2f0e678a2a403502bce712d34d8e7917a01edf10` (PR #48) and head `2798b198934cb51fe6a80ededcdf673caad31e02` (learning branch).
- **P2 marked DONE at branch/test level**; no live provider round-trip or deployment.
- PR #82 created as a mergeability probe from worker-host readiness (#64) to chat+learning branch (#81). GitHub reports mergeable=true; however, the observed workflow run checks out PR #64's merge ref, not PR #82's integration merge, so combined CI is NOT yet verified.
- **P4.3 IN PROGRESS:** identity/OIDC/worker stack integration and exact merge-ref CI evidence.

### 2026-11-22 — P4.3 worker/OIDC integration verification
- PR #82 mergeability refreshed: clean/mergeable. GitHub synthetic merge commit: `ea80e8c35dc923afcd3ed1f3b19aea60e1931c12`.
- Crucially, found PR #82-specific pull_request run **45046895853**, which checked out `refs/remotes/pull/82/merge` (not PR #64's merge ref). Combined exact merge-ref test suite passed: **1179 passed, 1 warning in 25.86s**.
- This merge-ref includes worker/OIDC readiness (#64 stack) with PR #81 base (chat/provider + governed learning). PR #82 remains draft/unmerged.
- **P4 marked DONE at branch integration/test level.** P5 live end-to-end readiness is **BLOCKED** by lack of verified live runtime and deployment approval boundary.

### 2026-11-22 — P5.1 release smoke checklist
- **P5.1 DONE:** created `docs/PROFESSOR_RELEASE_SMOKE_CHECKLIST.md` covering approvals, configuration/secrets, health/readiness, identity/tenancy, iPhone Safari, local reasoning, learning, worker safety, evidence and rollback.
- Current readiness code reports hosted login services missing/not implemented and `live_provider_round_trip_verified=false`. The local provider guide confirms self-hosted-first configuration but requires same-host setup and a real conversation test.
- **P5 remains BLOCKED** until a safe runtime target and deployment/test approval exist; no deployment was performed.
