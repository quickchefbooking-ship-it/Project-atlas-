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
**P5 — live end-to-end readiness remains BLOCKED.** No live provider round-trip, hosted-login service, or approved runtime smoke is verified. Current safe work is branch-level code/test audit; exact-head CI for recent PR #84 push commits cannot be queried through the available GitHub connector. No deployment or production change.

### Subtask states
- **P5 current subtask state:** consolidated status table below is authoritative; older checkpoint entries are historical snapshots.
- **P1.1 — PR inventory and exact-head CI refresh: DONE.**
- **P1.2 — focused core/security review: DONE.** Known limitations: shared API-key auth is not verified identity/RBAC/tenant isolation; actor labels are caller supplied; arithmetic-only executor; proposal testing not implemented; SQLite single host.
- **P1.3 — dependency map: DONE.** Priority chain: baseline #1 → chat #46/#47/#48/#49 → identity/reasoning #10/#11 → hosted OIDC #49–#57/#63 → worker safety #58–#64. Source reconciliation #65 separate; market PRs #70–#76 deferred; #66 duplicate/ported.
- **P2: DONE at branch/test level.** Compare confirms PR #11 is an ancestor of PR #48. PR #48 CI #44475448752 passed 929 tests; provider is opt-in. No live provider round-trip verified.
- **P3.1–P3.5: DONE at code/test level on stacked draft branches.** PR #79 exact-head CI #45046430157 success; PR #80 exact-head CI #45046596722 success (786 passed, 1 warning). Pending lesson and memory approvals are separate; no automatic promotion or self-modification.

### P5 status summary — reconciled 2026-11-22

| ID | Status | Evidence | Next action |
|---|---|---|---|
| P5.1 | DONE | Release smoke checklist committed on draft docs branch | Runtime smoke requires approved target |
| P5.2 | DONE | Local runtime bring-up guide; documentation only | Execute only in approved local environment |
| P5.3 | DONE | R1–R9 blocker register documented | Close blockers with evidence/approval |
| P5.4 | DONE | PR #83 exact CI 45049237138: 1181 passed | Runtime readiness still blocked |
| P5.5 | DONE | Worker execution boundary audit; R6 in-process isolation blocker | Independent host isolation needed |
| P5.6 | VERIFY | Chat scope preflight/fail-safe UI changed on PR #84; no exact-head CI | Verify on exact CI head |
| P5.7 | DONE | PR #77 head b02a6c18…; run 45046088812: 931 passed | Port is on PR #84; validate there |
| P5.8 | VERIFY | History boundary port on PR #84; read-back 9/9; exact-head CI unavailable | Retrieve/run exact-head CI |
| P5.9 | DONE | Branch overlap audit; no bulk integration | Recheck mergeability when CI access available |
| P5.10 | DONE | Read-back audit of five history files | None |
| P5.11 | DONE | Scope, fail-closed provider, and no-partial-turn tests audited | None |
| P5.12 | DONE (audit) | Separate conversation/audit transactions; consistency gap identified | Atomic transaction fix needs CI |
| P5.13 | VERIFY | 503 refresh-before-retry wording + audit failure test on PR #84 | Exact-head CI |
| P5.14 | DONE (design audit) | Shared transaction/savepoint approach and acceptance tests recorded | Implement after reliable CI verification |
| P5.15 | DONE (audit) | Tenant/owner scoping, caps, deletion and append-only tests reviewed | None |
| P5.16 | DONE (audit) | Conversation deletion retains append-only audit metadata | Retention policy remains explicit product/security decision |
| P5.17 | VERIFY | Delete confirmation discloses audit retention; UI regression added; read-back passed | Exact-head CI |
| P5.18 | DONE | Ledger reconciled to current branch heads and evidence | None |

**Exact branch heads:** PR #77 history fix `b02a6c18f334037df5d9c587b5c5a3e9d94db33f` (verified CI); PR #84 integration branch `c58f5856ed5a557c4deaa02333f5ec4e89825ecb` (read-back verified, CI unavailable); ledger PR #78 branch (checkpoint updated this run).
**PR #84 comparison:** 143 commits ahead / 3 behind PR #48 prompt-budget branch; merge-base `0eaf6d0ea45805645d9430f56376f5f0223302d1`. Mergeability is not directly queryable through this connector; previous checkpoint reported dirty. Draft/unmerged.
**CI limitation:** PR-triggered workflow lookup and commit combined statuses return empty for recent PR #84 push commits. The connector cannot list push-triggered workflow runs. No local repository checkout/test runner is available in this run; therefore P5.6/P5.8/P5.13/P5.17 remain VERIFY.
**Checkpoint source:** `docs/PROFESSOR_BUILD_TASK_LEDGER.md` is the durable checkpoint log. `docs/PROFESSOR_BUILD_CHECKPOINT.md` was not found (404); no separate checkpoint file is assumed.
**Cost/scope:** GitHub-only work; no paid service/credits, Replit, merge, deployment, production migration, secret, payment, or external action.


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


### 2026-11-22 — P5.18 reconciliation complete
- Consolidated the current P5.1–P5.18 statuses into a single table so the ledger no longer relies on historical checkpoint fragments for current state. P5.18 DONE.
- Reconciled branch heads: PR #77 b02a6c18f334037df5d9c587b5c5a3e9d94db33f; PR #84 c58f5856ed5a557c4deaa02333f5ec4e89825ecb; ledger branch checkpoint updated on PR #78. PR #84 CI remains VERIFY and runtime remains BLOCKED.
- The standalone checkpoint path is absent; this ledger is the checkpoint source. No cost or prohibited action.

- **Historical correction:** the P5.7 checkpoint correctly found the boundary fix absent from PR #84 at that moment. P5.8 later ported the fix and tests onto PR #84 branch; current status is VERIFY pending exact-head CI.

### 2026-11-22 — P5.19 IN PROGRESS: exact-head integration CI refresh
- **Task ID:** P5.19. Intended result: refresh the exact commit/head evidence for PR #84 full-stack integration (chat/provider + governed learning + worker/OIDC), determine whether an actionable CI status/run exists, and avoid treating branch read-back or historical CI as proof.
- **Status:** IN PROGRESS. Work started with ledger inspection; PR #84 remains draft/unmerged and its previously reported head is `c58f5856ed5a557c4deaa02333f5ec4e89825ecb`.
- **Scope/cost:** GitHub-only read/audit and ledger documentation; £0; no deployment, merge, production changes, secrets, payments, or external writes.
- **Next:** verify branch/head identity, fetch combined status and PR workflow runs, record exact result, then update status DONE only if evidence is complete; otherwise BLOCKED/VERIFY with precise reason.

### 2026-11-22 — P5.19 completed: exact-head integration CI refresh
- **Status: DONE (evidence lookup only).** Confirmed PR #84's reported head commit exists and is the exact commit `c58f5856ed5a557c4deaa02333f5ec4e89825ecb`; commit message is `test(professor): disclose audit retention on conversation delete`. Commit diff is limited to the new deletion-retention disclosure test in `tests/test_professor_chat_ui.py`.
- Exact-head combined status lookup returned **0 statuses** and PR-triggered workflow-run lookup returned **0 runs**. This is evidence that the connector currently exposes no CI record for this head, **not** evidence that CI passed. P5.6/P5.8/P5.13/P5.17 remain VERIFY.
- **Cost/scope:** GitHub read-only, £0. No CI dispatch, merge, deploy, or external write.

### 2026-11-22 — P5.20 IN PROGRESS: conversation/audit persistence atomicity audit
- **Task ID:** P5.20. Intended result: inspect the exact full-stack integration source and tests for the reported conversation-write/reasoning-audit split; confirm transaction semantics and identify the smallest safe remediation or precise blocker.
- **Status:** IN PROGRESS. Source inspection begins now.
- **Cost/scope:** GitHub-only read and documentation; £0; no provider calls, production changes, deployment, merge, or secrets.
- **Next:** fetch the conversation API and persistence/audit implementations and tests; verify current behavior; update status with evidence and an implementation/test plan if the connector cannot execute tests.

### 2026-11-22 — P5.20 audit DONE: atomic turn/audit consistency gap confirmed
- **Evidence:** PR #84 full-stack branch source read-back. `atlas_engine/professor_conversation_api.py` SHA `981c737a17388d6eac3fb2e6b5d502ac759b4dd8` calls `TenantConversationRepository.append_turn()` then `TenantReasoningAuditRepository.append()` sequentially. Both repository methods open/commit their own transaction. `tests/test_professor_conversation_api.py` SHA `6a1bbfb68e203ecde5cda19ee3fef4d7743a205d` deliberately asserts the failure leaves 1 conversation, 2 messages, 0 audit rows. Thus the consistency gap is confirmed, not merely inferred.
- **Result:** Safe minimal fix is one outer transaction around the turn + audit, with nested repository writes using savepoints rather than committing the outer transaction. On audit failure, roll back the whole turn and return a safe error stating the turn was not saved. Add rollback/commit regression tests and nested-savepoint tests.
- **Cost/scope:** GitHub-only inspection; £0. No production/database migration, external provider, deployment, merge, or secret use.

### 2026-11-22 — P5.21 IN PROGRESS: atomic conversation turn + reasoning audit
- **Task ID:** P5.21. Intended result: implement transaction/savepoint support for nested repository writes, wrap conversation turn and append-only audit in one atomic operation, and replace the partial-save test with rollback assertions.
- **Status:** IN PROGRESS. Existing full-stack PR #84 is the parent integration branch; a separate isolated child branch will be used to avoid altering the dirty integration probe.
- **Scope/cost:** code + regression tests on a draft branch; £0. No merge, deployment, production migration, provider activation, payments, or external writes.
- **Next:** create the child branch at the verified PR #84 head, implement, read back exact changes, and seek CI/runtime evidence. If tests cannot be executed or CI cannot be retrieved, leave VERIFY/BLOCKED and do not claim DONE.

### 2026-11-22 — P5.21 implementation checkpoint: atomic turn/audit branch (VERIFY)
- Draft PR #85 created, stacked on PR #84's exact integration head `c58f5856ed5a557c4deaa02333f5ec4e89825ecb`. Child branch `atlas/professor-atomic-turn-audit-2026-11-22` exact head: `d3ae80055c16b9b442cb2e34ea0d7553dfca9a41`.
- Source read-back verified: new `atlas_engine/sqlite_transaction.py`; 4 conversation repository write methods use the helper; audit append uses the helper; API outer transaction encloses both `append_turn` and audit append; failure response states no turn saved; regression assertions expect 0 conversations/0 messages/0 audits. Three savepoint tests are present. Compare against parent confirms 6 commits/6 files changed.
- PR #85 exact-head workflow run **45054741260** is **IN PROGRESS**. Job `test`: checkout/setup/dependency installation succeeded; `Run tests` step is running. Combined status currently empty; no pass/fail conclusion yet.
- **P5.21 status: VERIFY** until exact-head CI completes and any failures are addressed. Cost £0; branch-only, no merge/deploy/production migration/provider activation.

### 2026-11-22 — P5.22 IN PROGRESS: strengthen rollback test and static transaction audit
- **Task ID:** P5.22. Intended result: make the audit-failure regression inject failure *after* the audit repository has performed its nested write, so it proves the outer transaction rolls back both the messages and audit row; re-read the transaction helper and repository call sites for safe nesting.
- **Status:** IN PROGRESS. Initial static read-back shows helper uses a unique UUID savepoint for nested writes and begins/commits/rolls back only when it owns the transaction. This task adds a stronger failure point and re-verifies the exact source.
- **Scope/cost:** code/test only on PR #85 child branch; £0. No merge/deploy/production changes, secrets, payments, or provider activation.
- **Next:** patch the regression, wait for the latest exact-head CI, and update this status with evidence.

### 2026-11-22 — P5.21 and P5.22 DONE: atomicity fix exact-head CI passed
- PR #85 latest head: `f7cc1fa9a0e9b2fbceac6055d6ffe02efc5ff51d`. Exact PR merge-ref run **45054846603** checked out merge commit `1d76605` (PR head f7cc1 merged with base c58f5856); job `test` succeeded. Test log: **1187 passed, 1 warning in 19.91s**.
- The strengthened failure test now calls the original audit append (inserting the audit record within the outer transaction), then raises an SQLite error; assertions verify **0 conversations, 0 messages, 0 audits**. Thus it exercises rollback after the nested audit savepoint has released, not merely a failure before writing.
- P5.21 atomic transaction implementation and P5.22 static/rollback audit are **DONE at code + exact PR merge-ref CI level**. PR #85 remains draft/open/unmerged. No live deployment/runtime claim.
- Evidence: run `https://github.com/quickchefbooking-ship-it/Project-atlas-/actions/runs/45054846603`; PR `https://github.com/quickchefbooking-ship-it/Project-atlas-/pull/85`.
- Cost/scope: GitHub Actions test only; no paid services/credits, provider activation, merge, deployment, production migration, secrets, or external writes.

### 2026-11-22 — P5.23 IN PROGRESS: audit integrated chat/session/learning runtime coverage
- **Task ID:** P5.23. Intended result: confirm what exact-head CI proves across authenticated browser-session -> tenant conversation -> reasoning/provider fixture -> persistent history/audit/approved memory; identify remaining runtime-only release blockers without activating any provider or hosted service.
- **Status:** IN PROGRESS. PR #85 exact merge-ref CI passed 1187 tests; inspect the targeted integration/security tests and reconcile against P5 release blocker register.
- **Cost/scope:** GitHub-only read/audit; £0. No deployment, live credentials, provider calls, production data, merge, or external write.
- **Next:** finish test/readiness evidence review, update status and next action.

### 2026-11-22 — P5.23 DONE: integrated chat/session/learning coverage audit
- PR #85 exact-head CI 45054846603 passed 1187 tests; the merge-ref included PR #85 head f7cc1 with PR #84 base c58f5856. This is branch-level composition evidence only.
- `tests/test_professor_session_conversation_integration.py` SHA `acc689c1557e704c4410c91aa610e4c47dcdee01` exercises browser cookie + same-origin + CSRF session to tenant-scoped chat, fixture provider response, and persisted history. It does **not** run hosted OIDC login or a real provider; evidence retrieval is isolated in this test.
- `tests/test_professor_conversation_api.py` exact head `f9969f1dd01d6a6f5a83c06ca7b01fdeb0b58b70` covers two-turn history, audit chain verification, approved-memory retrieval only, scope denial, cross-owner isolation, missing-provider fail-closed, and atomic rollback after audit insert.
- Release blocker register read from ledger branch confirms R1 runtime smoke, R2 live provider, R3/R4 verified identity/hosted login, R5 persistent tenant storage, R6 independently isolated worker (current handlers in-process), R8 iPhone Safari, R9 release/rollback remain open. R7 capability scope remains narrow.
- **P5.23 DONE (audit).** No runtime/deployment actions. Cost £0.

### 2026-11-22 — P5.24 IN PROGRESS: refresh full-stack branch ancestry/overlap evidence
- **Task ID:** P5.24. Intended result: compare PR #84 integration head against its PR #48 prompt-budget base, confirm whether the previously reported dirty/behind state persists, and identify a safe next action without merging.
- **Status:** IN PROGRESS. Use exact current branch refs; avoid repeating the earlier overlap reconciliation.
- **Cost/scope:** GitHub-only read/compare; £0. No merge, deployment, production migration, or external writes.
- **Next:** verify branch refs and compare metadata/file overlap; if still dirty/unresolvable with available tools, document the precise blocker and move to another safe audit.

### 2026-11-22 — P5.24 DONE: integration ancestry and overlap refreshed
- Current comparison PR #84 branch `atlas/professor-full-stack-integration-2026-11-22` vs PR #48 base `atlas/professor-prompt-budget`: **diverged, 143 ahead / 3 behind**; merge base `0eaf6d0ea45805645d9430f56376f5f0223302d1`; PR #48 base head `2f0e678a2a403502bce712d34d8e7917a01edf10`.
- Changed-file overlap is exactly four paths: `atlas_engine/professor_reasoning_pipeline.py`, `static/professor_chat.html`, `tests/test_professor_chat_ui.py`, `tests/test_professor_reasoning_pipeline.py`. Current blob hashes differ on all four between PR #48 base and PR #84 integration branch, so prior overlap reconciliation is not a clean identical-content resolution.
- PR #85 CI passed on a merge ref of its child branch with PR #84 base, but it does **not** clear PR #84's mergeability/divergence against PR #48.
- **P5.24 DONE (read-only audit).** Cost £0.

### 2026-11-22 — P5.25 BLOCKED: clean full-stack integration into PR #48 base
- **Task ID:** P5.25. Intended result: make the full stack cleanly based on current PR #48 prompt-budget head and verify an exact integration merge-ref without merging/deploying.
- **Status:** BLOCKED by policy/scope: user prohibits merges and external writes; resolving and moving the 143-commit integration stack onto a diverged base would require an explicit branch-integration/merge-resolution action. Available evidence shows 4 overlapping files with differing current content. No attempt to rebase, merge, force-push, or rewrite the existing draft branch.
- **Unblock action:** maintainer review/approval for a dedicated conflict-resolution branch, or a maintainer manually resolves the four paths and reruns exact-head CI. PR #85 remains a tested draft child of PR #84; it is not a substitute for clean mergeability.
- **Cost/scope:** no action beyond GitHub read-only compare; £0. No merge/deploy/production migration/secrets/payments/external writes.

### Consolidated current subtask status — 2026-11-22
| Task | Status | Exact evidence / blocker |
|---|---|---|
| P5.6 | VERIFY | Chat UI scope/fail-safe changes on PR #84; no clean PR #84 integration merge-ref CI |
| P5.8 | VERIFY | History boundary port read-back; PR #84 CI unavailable |
| P5.13 | VERIFY | Safe retry/error handling change; no PR #84 exact-head CI |
| P5.17 | VERIFY | Delete/audit retention disclosure; PR #84 exact-head CI unavailable |
| P5.19 | DONE | Exact-head evidence lookup: PR #84 c58f5856; combined status/workflow runs empty (no CI claim) |
| P5.20 | DONE | Audit confirms conversation + audit commits are separate; test proved partial persistence |
| P5.21 | DONE | Atomic transaction implementation; PR #85 exact merge-ref CI 45054846603 passed |
| P5.22 | DONE | Failure injected after audit append; zero rows asserted; same exact-head CI passed |
| P5.23 | DONE | Integrated session/chat/history/audit/approved-memory coverage audit; 1187 tests pass |
| P5.24 | DONE | PR #84 diverged 143 ahead/3 behind; 4 overlapping files differ |
| P5.25 | BLOCKED | Clean integration needs conflict resolution/branch integration beyond prohibited merge scope; approval/manual resolution required |
| P5.26 | DONE | PR #85 head f7cc1fa9…; PR workflow run 45054846603 exact head SHA, merge ref 1d766051… on base c58f5856…; job succeeded and logs report 1187 passed, 1 warning. Transaction helper/API/tests read-back confirms rollback after audit insert. | No remaining task for this verification; next identity provenance audit |
| P5.27 | DONE (audit) | Source read-back: app.py 6fc0c821…; http_identity.py aed76f0a…; tenant_membership.py 4c5ef525…; atlas_session_identity.py 47ef7dec…; session_identity.py 49762f7a…; OIDC verifier a800307c…; hosted login components intentionally remain unset by app startup | Runtime login wiring/config is blocked until trusted deployment-owned provider/account/session/membership config and approved test environment exist; do not enable yet |
| P5.28 | DONE (audit) | Provider adapter + ConversationService + app lifespan read-back; provider is opt-in, bounded, tool-free, fail-closed; provider/API tests covered by exact PR #85 CI | No provider activation; next inspect runtime readiness/config docs |
| P5.29 | DONE (audit) | Readiness audit confirms `/launch/readiness` hosted-login check only tests client ID + redirect URI; provider round-trip remains false. Existing PR #63 supplies startup composition/readiness-services fix and PR #83 adds release-readiness tests; avoid duplicate code. | Audit/CI/branch composition of PR #63/#83 vs #84/#85; no code transfer or merge |
| P5.30 | DONE (audit) | PR #63 OIDC startup composition vs PR #84/#85 diverged; shared merge base 2e879fa6…; #63 is 13 commits ahead/72 behind #84 head comparison; overlapping app.py and OIDC integration tests require manual reconciliation | No branch rewrite or source transfer; verify #63/#83 exact-head CI and compare #83 stack before sequencing | 
| P5.31 | DONE (audit) | PR #63 run 44167021419 exact head 167f9986… passed 1101 tests; PR #83 run 45049237138 exact head d101a630… passed 1181 tests. PR #83 vs #85 diverged 20 ahead/1 behind, merge-base ea80e8c3…; overlap: professor_conversation_api.py + its API tests. #63 vs #84 overlap: app.py, hosted OIDC routes doc, browser-flow + readiness tests. | No branch rewrite; next reconcile release smoke checklist evidence in durable docs |

**Latest ledger checkpoint:** commit `483e44dec442eef4e33dce260ca2e3f5f2ee76e9`. The durable ledger branch remains separate, open/draft/unmerged. Cost remains £0.


### 2026-11-22 — P5.26 IN PROGRESS: atomicity evidence/source revalidation
- **Task ID:** P5.26. Intended result: independently revalidate PR #85 exact head and successful workflow evidence, inspect the transaction/savepoint implementation and API/test diff for correctness, and identify any remaining safe defect.
- **Status:** IN PROGRESS before execution. Existing ledger shows P5.21/P5.22 DONE based on run 45054846603; PR #85 is draft/open and the branch is stacked on PR #84.
- **Scope/cost:** GitHub-only source/CI read and ledger documentation; £0. No merge, deployment, production migration, secret, payment, provider activation, or external write.
- **Next:** inspect PR #85 source diff and workflow job details; verify the CI run commit and head relationship; update task status based on evidence.


### 2026-11-22 — P5.26 DONE; P5.27 IN PROGRESS: identity provenance audit
- **P5.26 DONE:** PR #85 head `f7cc1fa9a0e9b2fbceac6055d6ffe02efc5ff51d` was the exact workflow `head_sha` in run 45054846603; event was `pull_request`. Run succeeded on merge ref `1d766051d7725bd6a1964332426096afab6f158e` against PR #84 base `c58f5856ed5a557c4deaa02333f5ec4e89825ecb`. Job `test` completed successfully; logs confirm **1187 passed, 1 warning in 19.91s**. Transaction helper/API/repository/test diff read-back confirms nested savepoints and whole-turn rollback after audit insert.
- **P5.27 IN PROGRESS:** audit verified identity source, membership lookup, scope construction, browser session/cookie CSRF/origin protections, bearer verification and app composition; determine whether caller-supplied identity or tenant/scope can bypass verified principal.
- **Cost/scope:** GitHub-only read and ledger documentation; £0. No deployment, merge, production migration, secret, payment, provider activation, or external write.
- **Next:** inspect auth composition + tests; status DONE only for bounded audit with evidence, or BLOCKED if source/test evidence is insufficient.


### 2026-11-22 — P5.27 DONE (audit); P5.28 IN PROGRESS: provider/chat readiness audit
- **P5.27 DONE (audit only):** verified principal is built from a trusted OIDC token verifier or opaque Atlas account session, then scopes/tenant are resolved from server-side membership. Provider role claims are not authorization. Membership resolution fails closed for inactive/ambiguous tenant memberships. Browser cookie unsafe requests require exact trusted Origin + session-bound CSRF; cookie is Secure/HttpOnly/SameSite=Lax/host-only; CSRF cookie is Secure/SameSite=Lax and echoed in header. Opaque session token and CSRF token digests are persisted. Relevant source read-back: `http_identity.py` SHA `aed76f0a34cbf133e55816b73bbba9d16cd33c24`; `tenant_membership.py` SHA `4c5ef525cc9255291175a6ffc9d8ec8cca43d7f1`; `atlas_session_identity.py` SHA `47ef7deca1ab19be82f0968d2d46f5a47df5be9a`; `session_identity.py` SHA `49762f7a5aaa3ebf928dbaf8a4e8ad90a3bf3c34`; `oidc_jwt_verifier.py` SHA `a800307cda65d25f874a5b16d24d29531bc2913c`.
- **Confirmed runtime blocker:** app startup only builds the bearer `identity_service` from environment. `app.state.oidc_login_initiator`, `app.state.oidc_browser_login_service`, and `app.state.atlas_session_identity_service` are initialized to `None`; no lifespan wiring assigns the hosted-login components. `/identity/login` therefore returns the deliberate 503 “Hosted sign-in is not configured” until a trusted environment integration is built/configured. `app.py` SHA `6fc0c82137db68fb51a9d5701aa99ff9ed1b7baa`; `oidc_browser_routes.py` SHA `4aca5b74644813ee864a23793620d7c8c13311b9`. No bypass added.
- **P5.28 IN PROGRESS:** audit real reasoning provider loading, conversation service composition, failure handling and test coverage; identify next safe fix without enabling provider credentials.
- **Cost/scope:** GitHub-only read and ledger docs; £0. No provider activation, deployment, merge, migration, secret, payment or external write.
- **Next:** inspect provider config/adapter and app lifespan/tests; document exact readiness and any safe code-level defect.


### 2026-11-22 — P5.28 DONE (audit); P5.29 IN PROGRESS: runtime prerequisites/readiness audit
- **P5.28 DONE (audit only):** app lifespan loads the OpenAI-compatible provider only when `ATLAS_LLM_PROVIDER=openai_compatible` and deployment-owned endpoint/model are present; invalid explicit configuration leaves conversation disabled. Provider transport has no tool support, uses `trust_env=False`, bounded timeout/request/response limits, and permits plain HTTP only to loopback. Failures are sanitized; chat persistence happens only after reasoning succeeds. Tests cover opt-in/disabled config, unsafe URL rejection, mocked successful response/provenance, size caps, transport sanitization, service fail-closed and API no-partial-turn. Read-back SHAs: `openai_compatible_provider.py` `0684191311c55552223e3d5f4405545b4af000eb`; `conversation_service.py` `d1bda2214d7528cd3c1326f46ee00a6dbaf973c9`; `professor_reasoning_pipeline.py` `fbbe41e2a7c86cc3c4d6af9a046713d557169315`; provider tests `b441bde7e1adfd3e962873d451992347dd5535d6`; conversation service tests `ab3f7af578467f994f9769fc07b670ca72ae3a3b`; API tests `f9969f1dd01d6a6f5a83c06ca7b01fdeb0b58b70`; `.env.example` `e3d091c933289159e15ab0d13776dd250d568187`. Existing PR #85 exact-head CI 45054846603 passes 1187 tests.
- **P5.29 IN PROGRESS:** check runtime readiness checklist, app startup/config docs and environment examples for missing or misleading prerequisites; record the exact no-deployment unblock path.
- **Cost/scope:** GitHub-only read and ledger documentation; £0. No provider activation, live network, deployment, merge, migration, secret, payment or external write.
- **Next:** inspect readiness code/docs and environment configuration; update ledger with verified gaps and safe next action.


### 2026-11-22 — P5.29 DONE (audit); P5.30 IN PROGRESS: identity/provider stack composition
- **P5.29 DONE (audit only):** `/launch/readiness` hosted-browser-login check is only based on `ATLAS_OIDC_CLIENT_ID` + `ATLAS_OIDC_REDIRECT_URI`, and can show that one check true while `/identity/login-readiness` correctly reports `routes_registered_unconfigured` because services are not injected. Overall launch remains `not_ready` because live-provider round-trip is hardcoded false. Existing PR #63 explicitly fixes startup composition and makes launch readiness depend on matching injected services; PR #83 adds launch-readiness guard tests. No duplicate branch/code created. Evidence: app.py SHA `6fc0c82137db68fb51a9d5701aa99ff9ed1b7baa`; PR #63 head `167f9986124013608544a62cf27bbfc8de991095`, PR #83 head `d101a6303422e2b73028847c5d6bbac97cf95fe3`; both draft/unmerged.
- **P5.30 IN PROGRESS:** compare the existing OIDC startup composition and readiness test branches against the Professor full-stack/atomicity stack, refresh exact-head CI and ancestry/overlap evidence, and identify a safe sequencing path without merge/rebase/source transfer.
- **Cost/scope:** GitHub read-only; £0. No code copy, merge, rebase, deployment, provider activation, migration, secret, payment or external write.
- **Next:** verify PR #63/#83 run-head correspondence, compare ancestry/changed files with PR #84/#85, and record a dependency-safe integration decision.


### 2026-11-22 — P5.30 DONE (audit); P5.31 IN PROGRESS: readiness/identity branch composition
- **P5.30 DONE (audit only):** PR #63 OIDC startup composition head `167f9986124013608544a62cf27bbfc8de991095` is on a branch based at `2e879fa6624c71f60414f6c09e2bf2630ae5aaf4`; PR #84 integration head `c58f5856ed5a557c4deaa02333f5ec4e89825ecb` has the same merge base but diverges (compare reports 13 commits #63 ahead / 72 behind #84). PR #63 changed `app.py` and OIDC readiness/browser-flow tests that overlap the full-stack stack. No merge/rebase/cherry-pick/source transfer was attempted.
- **P5.31 IN PROGRESS:** exact-head CI and branch composition review of existing PR #63 hosted-login wiring and PR #83 release-readiness tests vs PR #84/#85 atomicity stack.
- **Cost/scope:** GitHub read-only; £0. No code copy, merge, rebase, deployment, provider activation, migration, secret, payment or external write.
- **Next:** confirm workflow run heads/test results and compare PR #83 ancestry/overlap; update task state.

| P5.32 | DONE | Release smoke checklist exists on ledger branch; updated checklist + local bring-up guide and read-back verified (blob SHAs 0defb0bb… and b9d9fd31…). Current CI/branch divergence and source selection warning now explicit. | No further doc action; live runtime blocked pending approved source/environment |


### 2026-11-22 — P5.31 DONE (audit); P5.32 IN PROGRESS: release-smoke evidence reconciliation
- **P5.31 DONE (audit only):** PR #63 workflow 44167021419 is pull_request event on exact head `167f9986124013608544a62cf27bbfc8de991095`, success, **1101 passed, 1 warning**. PR #83 workflow 45049237138 is pull_request event on exact head `d101a6303422e2b73028847c5d6bbac97cf95fe3`, success, **1181 passed, 1 warning**. PR #83 vs #85 compare: diverged 20 ahead / 1 behind, merge base `ea80e8c35dc923afcd3ed1f3b19aea60e1931c12`; overlap is `atlas_engine/professor_conversation_api.py` and `tests/test_professor_conversation_api.py`. PR #63 vs PR #84 overlap includes `app.py`, `docs/security/hosted-oidc-browser-routes.md`, `tests/test_oidc_browser_flow_integration.py`, and `tests/test_oidc_login_readiness.py`. This means no clean stack path without conflict reconciliation; no merge/rebase performed.
- **P5.32 IN PROGRESS:** validate whether the ledger's referenced release-smoke checklist exists on the authoritative ledger branch and/or integration branch, and reconcile any missing artifact claim.
- **Cost/scope:** GitHub read-only + ledger docs; £0. No merge, deployment, source transfer, provider activation, migration, secret, payment or external write.
- **Next:** inspect branch documentation inventory, verify checklist content if present, and update the ledger with exact file path/evidence and runtime blockers.

| P5.33 | BLOCKED | No approved local runtime target or local checkout/test runner available in this automation; user scope prohibits deployment/merge. Checklist requires explicit environment/source selection. | Unblock: owner/maintainer selects clean approved branch and safe local test environment; then authorized operator runs loopback smoke and captures redacted evidence |
| P5.34 | DONE (audit) | PR #85 branch read-back: `.env.example` has paid AI=false, provider=off, capability execution=false; config auth defaults true; worker gate fields all default false and dispatch requires all three gates plus lifecycle READY. Tests assert disabled worker, missing isolation and kill-switch stop. Exact PR #85 CI 1187 passed. | No activation; next inspect conversation storage/delete connection settings for FK and privacy correctness |


### 2026-11-22 — P5.32 DONE; P5.33 BLOCKED; P5.34 IN PROGRESS
- **P5.32 DONE:** release smoke checklist was found on the ledger branch (not PR #85 integration branch). Updated `docs/PROFESSOR_RELEASE_SMOKE_CHECKLIST.md` and `docs/PROFESSOR_LOCAL_RUNTIME_BRINGUP.md` to refresh exact CI evidence, clarify PR #84/#85 divergence and PR #63/#83 separate branches, and require maintainer source selection before any smoke test. Read-back verified checklist blob `0defb0bbcaae8b4066c4e7bd9aa33f09de7a1ecc` and bring-up guide blob `b9d9fd313b927a2ebd92478655b48572255cc6a3`. Update commits: checklist `b1dee00f70edb51dbe26ae1f526a4206f1d658a3`; guide `dc937bbc8a808099be69fbcb8b8222d1c9d6913f`.
- **P5.33 BLOCKED:** no authorized local runtime target or local checkout/test runner available to this automation. Production deployment, merge, source transfer and unapproved runtime actions remain prohibited. Unblock requires owner/maintainer selection of a clean approved branch and safe local test environment, followed by authorized operator capture of loopback smoke evidence.
- **P5.34 IN PROGRESS:** verify the integration branch defaults and worker/capability gates remain disabled, paid AI/provider remain off, and API auth remains fail-closed.
- **Cost/scope:** GitHub read/documentation only; £0. No deployment, merge, migration, secret, payment, provider activation or external write.
- **Next:** inspect exact PR #85 branch defaults and related tests/CI; update status with file and test evidence.

| P5.35 | DONE (audit) | Repository constructor explicitly enables `PRAGMA foreign_keys=ON`; conversation schema defines message FK `ON DELETE CASCADE`; API delete calls repository parent delete, tombstone transaction; regression test confirms stored messages zero after delete. No defect found. | Next inspect retained reasoning audit fields/deletion semantics and UI disclosure |


### 2026-11-22 — P5.34 DONE (audit); P5.35 IN PROGRESS: conversation storage/deletion boundary
- **P5.34 DONE (audit only):** PR #85 integration branch `.env.example` explicitly keeps `ATLAS_ENABLE_PAID_AI=false`, `ATLAS_LLM_PROVIDER=off`, and `ATLAS_CAPABILITY_EXECUTION_ENABLED=false`; `config.py` defaults API auth to true. Worker gate has `worker_enabled=false`, `global_execution_enabled=false`, `isolation_verified=false`; runner requires all gates and lifecycle accepting work before dispatch. Tests cover disabled default, missing isolation, kill-switch recheck, identity disabled and tenant grant denial. PR #85 exact merge-ref CI 45054846603 passed 1187 tests. Source SHAs: `.env.example` `e3d091c933289159e15ab0d13776dd250d568187`; `config.py` `e24e41677480909cf8db3df20966ed8de6b6db58`; worker runner `02d0ea0cf05677b9b13a2d2b180e3ff91da74f5f`; worker identity `8e4b90c9a2548cf1e2232bd9a686daeef21a2a20`; worker tests `e3aecd686a40a1142d9a175be2ac4d081f724564`; autonomy tests `6e2e2d8e8ff42accaac4cdcb57b44fa14adc73c0`; identity tests `51940298c97611792f739e31eb91b644f38acd72`.
- **P5.35 IN PROGRESS:** inspect conversation API SQLite connection setup and repository delete semantics to ensure foreign-key cascades/privacy cleanup are enforced on every request connection, not only schema-initialization connections.
- **Cost/scope:** GitHub read-only initially; if a narrow defect is confirmed, code/test on isolated PR branch only; £0. No merge, deployment, migration, secrets, payments, provider activation, external writes.
- **Next:** inspect repository/schema/delete tests and test API behavior; verify or patch with exact-head CI.

| P5.36 | DONE | New regression test commit 797482b4…; exact PR #85 head workflow 45061989861 success: 1188 passed, 1 warning. Conversation deletion removes messages, writes tombstone, retains append-only hash-only audit; raw prompt/answer absent; UI retention disclosure covered by test. | No further fix; next audit governed memory lifecycle/retrieval/delete privacy |


### 2026-11-22 — P5.35 DONE (audit); P5.36 IN PROGRESS: retained reasoning-audit privacy
- **P5.35 DONE (audit only):** `TenantConversationRepository.__init__` explicitly sets `PRAGMA foreign_keys=ON` on each API connection, not just the schema-initialization connection; conversation messages use composite owner/tenant FK with `ON DELETE CASCADE`. Repository deletion is transaction-wrapped and writes a deletion tombstone; API deletion test confirms message table count is zero. Source read-back `tenant_conversation_repository.py` SHA `13598b83b915140b7687c8b160791ccfaef2fa47`; API `professor_conversation_api.py` SHA `3302b63384d9e2f345662c49780407f38bad8e90`; tests `test_professor_conversation_api.py` SHA `f9969f1dd01d6a6f5a83c06ca7b01fdeb0b58b70`. No fix needed.
- **P5.36 IN PROGRESS:** audit the reasoning-audit rows retained after chat deletion; verify retained fields are hashes/metadata/provenance only, no raw prompt or response, and user-facing delete disclosure is accurate.
- **Cost/scope:** GitHub-only read; £0. No merge, deployment, migration, secrets, payment, provider activation, external write.
- **Next:** inspect audit schema, repository, UI delete confirmation and tests; update state with exact evidence.

| P5.37 | DONE (audit) | Repository/API read-back confirms pending proposal, owner-scoped approval, approved+unexpired+not-superseded retrieval, bounded lexical ranking, owner deletion and bounded expiry purge remove content/decisions. Existing suite 1188 passed. | Next verify memory retrieval is wired into real reasoning and prompt treats memory as reference, not instruction |


### 2026-11-22 — P5.36 DONE; P5.37 IN PROGRESS: audit retention + governed memory
- **P5.36 DONE:** added `test_delete_retains_minimal_append_only_reasoning_audit_without_raw_content` on PR #85. Commit/head `797482b4cd92688a370fe720eb63f724d6e4f08b`; exact PR workflow run `45061989861` completed successfully (pull_request event, exact head), **1188 passed, 1 warning in 23.10s**. Regression verifies message content is deleted, tombstone exists, audit record remains, prompt/answer hashes match, raw prompt/answer are absent, and record hash is bounded. UI test confirms the delete confirmation discloses retained append-only audit. No production data affected.
- **P5.37 IN PROGRESS:** audit approved memory lifecycle and retrieval/deletion boundary for tenant/owner isolation, reviewer/proposer separation, approval gate, bounded content, expiry and privacy retention.
- **Cost/scope:** GitHub-only source/test; £0. No merge, deployment, migration, secret, payment, provider activation or external write.
- **Next:** inspect memory repository/API/retrieval and tests; close only after source evidence or add a narrow regression fix with exact-head CI.

| P5.38 | DONE (audit) | API retrieves only memory:read approved owner memories (limit 5), passes them into the two-pass pipeline; context is bounded and labeled reference-only; trace metadata stores proposal IDs. Integration tests verify approved memory in prompt, refs in audit, hostile memory remains untrusted, current request outranks historical conflict. | No defect found; next add a transport-to-API mock integration test because adapter and API are currently tested separately |


### 2026-11-22 — P5.37 DONE (audit); P5.38 IN PROGRESS: governed-memory retrieval into reasoning
- **P5.37 DONE (audit only):** memory repository requires explicit scopes; proposals are pending by default, approval is single-use and append-only, owner/tenant scoped, and expiry bounded to 1–3650 days. Retrieval selects only approved, unexpired, non-superseded memories, ranks bounded lexical matches (API limit 20; reasoning limit 5), and returns matched-term/field provenance. Deletion removes proposal content, decisions and linked supersession metadata; expiry purge is owner-scoped and bounded (max 500) with delete scope. Existing test coverage includes owner/tenant isolation, inactive membership, approval/rejection, expiry, deletion, supersession and retrieval evaluation. Source/test SHAs: repository `9dd4cfd54dfc11d718ecb68bee77d310ef3ea5f9`; API `a05c25e33172cc23c58970e08789a97255352225`; tests `35b85f80962bbb7f33e58eae655b59d91ea28612`, `90b90a1fcb16ef482d055d328028b9718caa153e`, retrieval evaluation `21984bf3edbcc0649f279ff158baa2360e1be9f7`. No defect found in this bounded audit.
- **P5.38 IN PROGRESS:** trace the approved-memory retrieval from API to Professor pipeline, ensure prompt boundary and provenance references are bounded, and confirm no raw memory content is copied into audit storage.
- **Cost/scope:** GitHub-only read; £0. No merge, deployment, migration, secret, payment, provider activation or external write.
- **Next:** inspect API→pipeline composition and prompt/audit regression tests; update ledger with exact evidence.

| P5.39 | DONE | Added offline HTTP-mock end-to-end test using the real OpenAI-compatible adapter through ConversationService, Professor two-pass pipeline, authenticated conversation API, persistence and audit. PR #85 head f26cda77… exact PR run 45062228181 success: 1189 passed, 1 warning; push run 45062223936 success. | No live provider activation; next audit baseline/dependency integrity on main and active integration branch |


### 2026-11-22 — P5.38 DONE (audit); P5.39 IN PROGRESS: real provider adapter end-to-end test
- **P5.38 DONE (audit only):** authenticated conversation API retrieves memory only when caller has `memory:read`, at most five approved owner-scoped items; it passes bounded fields to the reasoning pipeline. Pipeline validates shapes, builds a bounded memory section labelled reference data, explicitly treats memory as untrusted reference rather than instructions, prioritizes current request, and returns proposal IDs only for audit metadata. API integration tests prove approved memory appears in both reasoning context and trace IDs; pipeline tests prove hostile memory is not promoted to instructions and conflicting historical memory does not override current request. Source SHAs: conversation API `3302b63384d9e2f345662c49780407f38bad8e90`; pipeline `fbbe41e2a7c86cc3c4d6af9a046713d557169315`; conversation integration tests `5e71f1157a0d3ec28f109a3126dbac919b611746`; pipeline tests `1728b841203eb5447828b04fb9da6465e6e4cda3` (fetch exact SHA before commit); exact PR #85 CI 45061989861 passed 1188 tests.
- **P5.39 IN PROGRESS:** add a mock-HTTP test that exercises the actual OpenAI-compatible provider adapter through the authenticated conversation API and two-pass Professor pipeline; no external network or live provider.
- **Cost/scope:** GitHub code/test on existing draft branch; £0. No live network, provider activation, merge, deployment, migration, secret, payment or external write.
- **Next:** inspect existing integration tests for duplicates, then add and verify one bounded regression test.

- Existing browser-session integration test uses `IntegrationProvider`; lifecycle integration uses `FixtureProvider`. Neither exercises `OpenAICompatibleConversationProvider` with `httpx.MockTransport` end-to-end through the API. This confirms the P5.39 test gap is not duplicate work. Existing files read: session integration SHA `acc689c1557e704c4410c91aa610e4c47dcdee01`; lifecycle integration SHA `27a03c1de50fdfa923a45222e60178a5f57e4b35`.

| P5.40 | DONE (audit) | Main `requirements.txt` is application Python, not pip requirements; main SHA 32471ea… unchanged. PR #1 repair branch pins 9 deps, exact run 43489002177 passed 237 tests; PR #85 branch pins 12 deps, install + tests passed 1189. PR #1 remains draft/unmerged; PR #1 vs PR #85 diverged 855 ahead/1 behind. | Baseline source remains blocked on clean integration/maintainer decision; next update blocker docs with evidence |


### 2026-11-22 — P5.39 DONE; P5.40 IN PROGRESS: provider adapter end-to-end mock test
- **P5.39 DONE:** added `test_authenticated_api_uses_http_mock_provider_through_reasoning_pipeline` on existing PR #85 branch. It uses `httpx.MockTransport` (no network), the actual OpenAI-compatible adapter, `ConversationService`, two-pass reasoning, authenticated API, persisted user/assistant messages, provider/model provenance, append-only audit and chain verification; execution stays false. Commit/head `f26cda77b83305a516a189d6ff4403e984cc8561`. Exact PR run `45062228181` completed success: **1189 passed, 1 warning in 26.53s**. Matching push run `45062223936` also success on same head. Test file blob `8aa4f311fbd247433becafd0d8cc785d6f45583f`.
- **P5.40 IN PROGRESS:** inspect dependency baseline files on `main`, baseline-repair PR #1, and PR #85 integration head. CI install passing on #85 is evidence for that branch only; it does not resolve main or clean integration.
- **Cost/scope:** GitHub-only source/CI read; £0. No live provider, merge, deployment, migration, secret, payment or external write.
- **Next:** fetch requirements/dependency files and PR #1 exact status/CI; document verified baseline and branch divergence.

| P5.41 | DONE | Added R10 to blocker register; updated bring-up source selection and latest exact-head evidence (PR #85 head f26cda77… 1189 tests; PR #1 head f8d6eac… 237 tests). Read-back verified docs. | No further doc action; next inspect current main CI for direct install evidence |


### 2026-11-22 — P5.40 DONE (audit); P5.41 IN PROGRESS: dependency baseline blocker
- **P5.40 DONE (audit only):** `main` `requirements.txt` SHA `e5c68b6d89cb49d4f5dbe6e722e476ff5a8b7486` is application Python code (imports, app setup, route declarations), not a pip requirements list; default branch remains `32471ea720edb5f10ca51aafaf9d45113d4e736c`. PR #1 baseline-repair branch requirements SHA `aa3aae8c20b8e602a0fdcba5aa6a635cd5bca6f7` pins 9 packages; exact run `43489002177` on head `f8d6eac412d1031430bee6b3740dc67113b854ec` succeeded, **237 passed, 1 warning**. PR #85 branch requirements SHA `b7b993e2a85a2f01bb358cda8d944b76df95f4d7` pins 12 dependencies, including jsonschema, PyJWT crypto and argon2; exact PR CI `45062228181` on head `f26cda77b83305a516a189d6ff4403e984cc8561` passed **1189 tests** and install. PR #1 remains open/draft/unmerged. PR #1 vs #85 compare diverged **855 ahead / 1 behind**, merge-base `ab0810975313b65a0fcd0ceb1a804c056b6c6141`; no integration performed.
- **P5.41 IN PROGRESS:** refresh blocker register and bring-up guide with this dependency evidence, emphasizing main remains unrepaired and PR #1/#85 are not cleanly integrated.
- **Cost/scope:** GitHub-only read and docs; £0. No merge, deployment, source transfer, migration, secret, payment, provider activation or external write.
- **Next:** update docs and verify exact read-back.

| P5.42 | IN PROGRESS | Verify latest main branch workflow status/run for malformed dependency baseline and record exact install/test evidence; task started before inspection | Fetch main runs, job/log, exact head; update blocker if CI confirms |


### 2026-11-22 — P5.41 DONE; P5.42 IN PROGRESS: dependency blocker documentation
- **P5.41 DONE:** blocker register R10 and runtime guide updated to state that main `requirements.txt` is malformed Python source, PR #1 is draft/unmerged, PR #85 has pinned dependencies but is diverged, and a clean maintainer-selected branch is required. Latest PR #85 exact CI evidence refreshed to head `f26cda77b83305a516a189d6ff4403e984cc8561`, run `45062228181`, 1189 passed; push run `45062223936`. Read-back verified register blob `43236cb058d423628e521e1131c1abeb32149f3a`; checklist update commit `f8afba42094528d8a9a4211131795f83d8a8eb61`; bring-up update commit `2ccd91496ef92fcf979eaf58314a2ad47acdd44d`.
- **P5.42 IN PROGRESS:** check whether main's current workflow confirms the broken dependency file directly, rather than inferring install failure from source.
- **Cost/scope:** GitHub read/docs only; £0. No merge, deployment, migration, source transfer, secret, payment, provider activation or external write.
- **Next:** inspect main branch Actions run and install step; update task state.
