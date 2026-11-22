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
- **P5.7 DONE (audit/verification)** — PR #77 exact head b02a6c18f334037df5d9c587b5c5a3e9d94db33f; workflow run 45046088812 succeeded with **931 passed, 1 warning (20.67s)**. The branch is 3 commits ahead of PR #48 prompt-budget head. PR #84 full-stack branch is diverged (134 ahead, 6 behind) and does not contain the fix: its conversation contract lacks MAX_HISTORY_MESSAGES, API lacks the 22-message repository limit, and its API test lacks the long-history regression. Integration still requires port + exact-head CI.
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
- Draft integration PR #81 targets PR #48 with PR #80 learning changes. Verified exact merge-ref workflow run **45046847109** checked out `refs/remotes/pull/81/merge` and passed **786 tests, 1 warning in 24.38s**.
- **P2 marked DONE at branch/test level**; no live provider round-trip or deployment.
- PR #82 is a mergeability probe from worker-host readiness (#64) onto PR #80 learning branch. Its exact merge-ref CI run 45046895853 passed 1179 tests, but **does not include PR #81 chat/provider branch**. Earlier combined claim was incorrect and is corrected below.
- **P4.3 IN PROGRESS:** identity/OIDC/worker stack integration and exact merge-ref CI evidence.

### 2026-11-22 — P4.3 worker/OIDC + learning integration verification (DONE, partial stack)
- PR #82 exact merge-ref run **45046895853** checked out `refs/remotes/pull/82/merge` and passed **1179 passed, 1 warning in 25.86s**.
- This integrates worker/OIDC readiness (#64) with learning (#80), but its base is #80, **not chat/provider PR #81**. Do not treat this as full-stack proof.
- **P4 remains IN PROGRESS** until PR #84 verifies chat/provider + learning + worker/OIDC in one exact merge-ref.

### 2026-11-22 — P5.1 release smoke checklist
- **P5.1 DONE:** created `docs/PROFESSOR_RELEASE_SMOKE_CHECKLIST.md` covering approvals, configuration/secrets, health/readiness, identity/tenancy, iPhone Safari, local reasoning, learning, worker safety, evidence and rollback.
- Current readiness code reports hosted login services missing/not implemented and `live_provider_round_trip_verified=false`. The local provider guide confirms self-hosted-first configuration but requires same-host setup and a real conversation test.
- **P5 remains BLOCKED** until a safe runtime target and deployment/test approval exist; no deployment was performed.

### 2026-11-22 — P5.2 local runtime bring-up prepared
- **P5.2 DONE (documentation preparation only):** added `docs/PROFESSOR_LOCAL_RUNTIME_BRINGUP.md` with loopback-only setup, provider-off first smoke, health/readiness/UI checks, cleanup, and evidence requirements.
- **P5 runtime execution BLOCKED:** no local computer/runtime execution is available from the GitHub connector; the user or approved test environment must run the documented smoke test and return exact evidence. No public exposure or deployment.
- Next: continue safe code/test review while runtime evidence remains pending; identify any further release blockers without altering deployment settings.

### 2026-11-22 — P5.3 release blocker register
- **P5.3 DONE:** added `docs/PROFESSOR_RELEASE_BLOCKER_REGISTER_2026-11-22.md` documenting verified blockers R1–R9, evidence required to close each, safe closure order, and prohibited actions.
- Re-verified code defaults: reasoning provider off; capability execution opt-in; health/readiness diagnostics explicitly do not prove a real provider conversation or login round trip.
- **P5 remains BLOCKED** pending R1 safe runtime evidence. Continue with code-level tasks that do not require live environment or approval.

### 2026-11-22 — P5.4 readiness false-positive guard tests
- **P5.4 IN PROGRESS:** added draft PR #83 with tests for `/launch/readiness` missing configuration and the rule that configured identity/storage/provider does not substitute for a live provider round-trip. Tests-only change.
- PR #83 refreshed to mergeable=true; exact-head workflow run 45049237138 is in progress. Do not mark complete until run conclusion and test evidence are checked.
- If CI passes, mark P5.4 DONE; P5 live runtime remains BLOCKED.

### 2026-11-22 — P5.5 execution boundary review
- **P5.5 DONE:** reviewed the actual tenant `execute-next` route and registered capability runtime. The global kill switch is checked before plan inspection/handler dispatch; however, bounded handlers run in the API process and Crossref network work is in-process. This is now explicitly recorded as an isolation blocker R6; worker-host readiness does not prove independent isolation.
- **P5.4 remains IN PROGRESS:** PR #83 mergeability refreshed to true; exact-head workflow run 45049237138 still in progress. Do not close until the test workflow finishes.

### 2026-11-22 — P5.4 readiness regression guard verified
- **P5.4 DONE:** PR #83 exact head `d101a6303422e2b73028847c5d6bbac97cf95fe3` run 45049237138 succeeded: **1181 passed, 1 warning in 21.30s**. PR refreshed mergeable=true. Tests cover absent configuration and prevent configured services from being confused with a verified live provider round-trip.
- Updated the CI evidence matrix with PR #83. Tests-only branch, draft/unmerged.
- **P5 still BLOCKED:** actual runtime smoke/provider/login/iPhone checks remain outstanding. Next safe task: review chat UI connection/error-state behavior and document any test gaps; no live provider activation.

### 2026-11-22 — integration ancestry correction and P4.4
- Corrected the evidence matrix and ledger: PR #81 is chat/provider + learning (exact merge-ref run 45046847109, 786 passed); PR #82 is worker/OIDC + learning (exact merge-ref run 45046895853, 1179 passed); PR #83 readiness tests are on worker+learning, not chat.
- **P4.4 IN PROGRESS:** PR #84 is the corrected full-stack integration probe, targeting PR #48 chat/provider with the PR #82 worker+learning merge stack. Exact merge-ref CI evidence is pending. Draft/unmerged; no deployment.

### 2026-11-22 — P4.4 conflict reconciliation attempt
- PR #84 full-stack probe created from the PR #82 merge stack and targets PR #48 chat/provider branch. GitHub reports `mergeable_state=dirty`; no merge-ref CI has been produced.
- Compared overlap paths from PR #48 and PR #82: three core reasoning files and two lifecycle/context test files are identical at the current content hashes. Conflicts are isolated to chat UI, chat UI tests, and reasoning pipeline prompt-budget test; these were manually reconciled on the draft branch, preserving OIDC/CSRF auth, provider metadata, safe retry messaging, explicit `professor:chat` scope check, and structured conversation history test.
- After reconciliation, PR #84 remains `dirty` and no CI run is available. **P4.4 BLOCKED** pending a clean branch integration/merge-ref. No merge/deploy.

### 2026-11-22 — P5.6 chat UI fail-safe review
- **P5.6 IN PROGRESS:** reviewed chat UI/API error flow. Found UI permission preflight omitted the API-required `professor:chat` scope; it could mark a user connected then fail only on send. Added explicit scope check on PR #84 integration branch.
- Reconciled UI to show provider/model/reasoning/execution metadata only after a successful response; user message remains in input on failure, no fake assistant answer is inserted, and status warns the server may have completed the turn before retry.
- Verified the updated UI/test files fetch back from GitHub. Full CI validation is blocked by PR #84's unresolved dirty merge state; do not mark P5.6 DONE until exact integration CI passes.


### 2026-11-22 — P5.7 started: history boundary CI/integration audit
- Task ID P5.7 IN PROGRESS. Before verification, PR #77 was confirmed open/draft with reported exact head b02a6c18f334037df5d9c587b5c5a3e9d94db33f. Intended result is to verify exact-head workflow/test evidence and determine whether the history boundary fix is included in PR #84's full-stack branch.
- Safe scope: GitHub-only read/isolated ledger documentation; no paid tools, deployment, merge, or external writes.


### 2026-11-22 — P5.7 verified; P5.8 started
- P5.7 DONE: exact-head run 45046088812 on b02a6c18f334037df5d9c587b5c5a3e9d94db33f completed successfully. Job log confirms 931 passed, 1 deprecation warning, in 20.67s. Commit diff centralizes MAX_HISTORY_MESSAGES = MAX_TURNS - 2, applies the same limit to API repository retrieval, and tests a 12-turn stored conversation yields 22 prior messages + system + latest user = 24 provider messages.
- Compare: PR #77 is 3 commits ahead of PR #48 head 2f0e678a2a403502bce712d34d8e7917a01edf10. PR #84 branch compare is diverged (134 ahead/6 behind) with merge base 0eaf6d0ea45805645d9430f56376f5f0223302d1; inspected branch files confirm it has not incorporated the API history limit/regression.
- **P5.8 VERIFY** — Ported the history boundary into PR #84 branch in five commits, latest d1686b0cf991b1aa3ddadbdeeaac9e0340f7fe73. Contract constant, API fetch limit, pipeline guard, long-history API regression, and pipeline 22-message acceptance/23-message rejection tests are present. Exact-head CI is not yet verifiable: PR-triggered workflow lookup returns none, combined status is empty, and this connector cannot list push-triggered runs. Do not mark DONE without exact-head CI.
- **P5.9 DONE (audit only)** — Compared PR #84 branch to PR #48: diverged, 139 ahead/3 behind, merge base 0eaf6d0ea45805645d9430f56376f5f0223302d1. Four changed-file overlaps: reasoning pipeline, chat HTML, chat UI tests, and pipeline tests. PR #84 branch includes PR #48 prompt-budget/context test changes but has additional hosted-session/auth and history-limit changes. No merge/rebase/bulk transfer attempted; connector cannot expose PR mergeability directly.
- **P5.10 DONE (read-back audit)** — Read all five files from PR #84 exact branch head d1686b0cf991b1aa3ddadbdeeaac9e0340f7fe73; 9/9 assertions passed: shared 22-message constant, API limit, pipeline guard, API and pipeline regressions, and 23-message rejection. No residual API limit=23 found. CI still unverified.
- **P5.11 DONE (audit)** — PR #84 conversation endpoint checks verified principal plus explicit professor:chat scope before provider work; missing provider fails closed. Tests assert provider failure leaves zero conversation/message rows and >4000-character output leaves zero rows. Provider exception detail is not exposed; API returns a generic 503. append_turn writes the user/assistant pair atomically.
- **P5.12 DONE (audit)** — Verified separate commits: append_turn commits the user/assistant pair first, then reasoning-audit append starts its own transaction. If the audit write fails, conversation content can remain saved without an audit record and API returns 503. This is a consistency gap; the UI already warns to refresh before retry. No atomic cross-repository transaction is implemented.
- **P5.13 VERIFY** — API storage-error guidance updated and a focused test added on PR #84 branch. Read-back checks pass, but exact-head CI is unavailable through this connector; the test intentionally documents current post-save audit failure state (turn saved, audit absent) and asserts refresh-before-retry guidance.
- **P5.14 DONE (audit/design)** — Conversation turn and reasoning-audit writes use separate transactions. Smallest safe fix is a shared transaction context supporting nested savepoints, with API outer transaction around append_turn + audit.append. Acceptance: audit failure rolls back both rows; success persists both; chain verification remains valid; standalone repository tests continue passing. No code refactor attempted without CI evidence.
- **P5.15 DONE (audit)** — Repository is scoped by verified tenant_id + hashed issuer/subject owner_key; read/write/delete scopes are enforced; IDs/content bounds are validated; 200-message cap; recent retrieval ordered correctly; delete cascades content and leaves minimal tombstone; append-only trigger and cross-owner/tenant tests exist. No gap found in reviewed paths.
- **P5.16 DONE (audit)** — DELETE removes the conversation row and cascades message content; the deletion log retains only tenant/owner pseudonym/conversation ID. Reasoning-audit records are separate, append-only, and remain after conversation deletion: hashes, provider/model, evidence references, and limited metadata. The UI confirmation does not disclose this retention; transparency gap identified.
- **P5.17 VERIFY** — PR #84 UI confirmation now discloses retained append-only reasoning audit (hashes, provider/model, evidence references, limited metadata); regression test added. Read-back assertions pass, but exact-head CI remains inaccessible (no PR-triggered runs/status checks returned).
- **P5.18 IN PROGRESS** — Reconcile ledger/checkpoint and exact branch heads after this cycle. Intended result: durable state is accurate, evidence is linked, and no task is mislabeled DONE.


### 2026-11-22 — P5.8 code port checkpoint; CI verification pending
- Ported the verified PR #77 history boundary to the existing PR #84 draft branch: shared MAX_HISTORY_MESSAGES = MAX_TURNS - 2; API repository retrieval now uses that constant; pipeline rejects history above 22; API test verifies 12 stored turns trim to 22 prior messages and exactly 24 provider messages; pipeline test accepts 22 and rejects 23.
- Five file commits were created on the existing integration draft branch; latest exact head d1686b0cf991b1aa3ddadbdeeaac9e0340f7fe73. Commit is present on GitHub; no merge/deployment.
- CI evidence limitation: commit workflow lookup (PR-filtered) returned no run; combined status returned no checks. Push workflow is configured for atlas/**, but the GitHub connector cannot list push-triggered workflow runs, so exact-head verification remains VERIFY. The already-verified PR #77 run is not substituted for this branch's CI.
- **P5.9 IN PROGRESS:** review overlaps/conflict paths between PR #84 full-stack branch and PR #48 target; do not attempt a bulk merge/rebase or source transfer.


### 2026-11-22 — P5.9 conflict-scope audit complete; P5.10 read-back started
- PR #48 changed paths: cognitive kernel, reasoning context/pipeline, chat HTML, chat UI tests, lifecycle integration, context tests, and pipeline tests. PR #84 changed paths overlap four of these: reasoning pipeline, chat HTML, chat UI tests, and pipeline tests.
- PR #84 branch has 139 commits ahead and 3 behind PR #48 (merge base 0eaf6d0ea45805645d9430f56376f5f0223302d1). It is a broad worker/OIDC/learning stack, so no bulk branch integration was attempted. Conversation contract/API changes introduced by the history fix are now on the PR #84 draft branch.
- P5.9 DONE as audit; mergeability remains not independently queryable through the available GitHub connector. **P5.10 IN PROGRESS** read-back verification of the port.


### 2026-11-22 — P5.10 read-back audit complete; P5.11 started
- Read-back from PR #84 branch head d1686b0cf991b1aa3ddadbdeeaac9e0340f7fe73 verified all five files and 9 checks passed: shared history constant, API retrieval limit, pipeline validation/error text, long-conversation API test, max-history pipeline test, and 23-message rejection. No residual API retrieval limit of 23.
- P5.10 DONE (repository read-back only). **P5.11 IN PROGRESS**: inspect auth/scope and failure persistence boundary with targeted source/tests; no runtime or provider activation.


### 2026-11-22 — P5.11 scope/failure-path audit complete; P5.12 persistence audit started
- PR #84 endpoint read-back: verified identity principal dependency and explicit professor:chat scope check precede provider work; service/config failure returns 503 before conversation creation; memory read requires memory:read; user and assistant turn writes are atomic through append_turn.
- Regression tests exist for provider failure (0 conversation rows/0 messages), provider output over 4000 chars (0 rows), and missing chat scope (403). Provider exception detail is hidden behind a generic 503. P5.11 DONE (audit evidence only).
- P5.12 IN PROGRESS: inspect conversation persistence and audit write ordering for potential consistency gap after provider success.


### 2026-11-22 — P5.12 persistence audit complete; P5.13 started
- Confirmed API order: atomic conversation append_turn commits the user/assistant pair, then the separate audit repository appends. A post-turn audit failure can leave a persisted turn without an audit entry. This is not a provider failure; route returns storage 503.
- Current UI warning already says server may have completed and to refresh before retry. API error wording is less precise. P5.12 DONE (audit only); cross-table atomicity is a remaining consistency gap.
- **P5.13 IN PROGRESS** — tighten 503 guidance and add a focused regression for post-save audit failure; no external action or deployment.


### 2026-11-22 — P5.13 code checkpoint; P5.14 transaction audit started
- PR #84 API error guidance now says the turn may already be saved and directs refresh before retry; a test simulates audit append failure and checks generic error/no backend detail. Read-back of API + test passed 6 checks on exact branch head 40b27a11e3652442e4a7c41b28406292d5aeb073.
- Exact-head CI remains unverified: PR-triggered runs/status checks are empty; push-run listing is unavailable. P5.13 VERIFY, not DONE.
- **P5.14 IN PROGRESS** — evaluate atomic transaction design and regression criteria; safe read-only audit only.


### 2026-11-22 — P5.14 transaction design audit complete; P5.15 repository scope audit started
- Atomicity gap confirmed: append_turn commits its own transaction; reasoning-audit append begins another. Proposed smallest safe correction: shared transaction context that uses SAVEPOINT when already in transaction; wrap both writes in one API-level outer transaction. Tests should assert audit-write failure rolls back conversation+messages, success writes both, and hash-chain verification still passes.
- No refactor attempted this run because exact-head CI evidence is unavailable through the GitHub connector and there is no local checkout/test runner. P5.14 DONE (audit/design only).
- **P5.15 IN PROGRESS** — read-only owner/tenant scoping and retention audit of conversation repository.


### 2026-11-22 — P5.15 repository isolation/retention audit complete; P5.16 deletion audit started
- Repository inspection confirms all conversation queries include tenant_id and owner_key, owner key is pseudonymous, read/write/delete scopes are checked, message roles/content/IDs are validated, max 200 stored messages, and retrieval returns ordered bounded recent history. Tests cover cross-user/cross-tenant isolation, same-ID owner separation, scopes, deletion cascade, tombstone minimality, append-only, and limits.
- P5.15 DONE (audit only). **P5.16 IN PROGRESS**: inspect delete route and reasoning-audit retention to ensure privacy behavior is explicit.


### 2026-11-22 — P5.16 deletion/privacy audit complete; P5.17 started
- DELETE route calls conversation repository delete only. FK cascade removes stored messages; deletion tombstone keeps tenant/owner pseudonym/conversation ID, no message text. Separate reasoning-audit table is append-only (no UPDATE/DELETE triggers) and has no conversation FK; audit records persist after conversation deletion, retaining request/response/context hashes, provider/model, evidence references and limited metadata.
- P5.16 DONE (audit only). Transparency gap: current confirmation says message content is deleted but does not disclose retained audit. **P5.17 IN PROGRESS**: add truthful disclosure and UI regression; do not change audit retention policy.


### 2026-11-22 — P5.17 UI disclosure checkpoint; P5.18 ledger reconciliation started
- Delete confirmation now accurately says conversation message content is removed while append-only reasoning audit hashes, provider/model, evidence references, and limited metadata remain for integrity verification. Added UI regression test. Read-back checks passed on exact PR #84 branch head c58f5856ed5a557c4deaa02333f5ec4e89825ecb.
- No audit retention policy changed. Exact-head CI remains unverified because PR-run lookup and commit statuses return empty; push-run list is not exposed by this connector. P5.17 VERIFY.
- P5.18 IN PROGRESS: final durable checkpoint reconciliation.
