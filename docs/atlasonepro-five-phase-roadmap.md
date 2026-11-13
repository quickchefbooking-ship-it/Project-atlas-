# AtlasOnePro Professor — Five-phase delivery roadmap

**Purpose:** a gated engineering plan for building the Professor into a reliable, secure orchestration system with specialist capability arms. This roadmap is a delivery plan, not a claim that future capabilities are already live.

## Programme rules

- Work in phase order. A phase is complete only when its acceptance tests and evidence are recorded.
- Preserve existing working systems and use the current recovery branch. Do not create duplicate projects.
- Keep paid services disabled unless Ashley explicitly approves them.
- Keep external integrations read-only or draft-only until their permissions, identity and approval controls are proven.
- Never merge, deploy, publish, change production or alter main without a separate explicit approval.
- A green test suite is necessary but not sufficient for production readiness.

## Phase 1 — Safe crash recovery

**Status: prototype implementation complete; awaiting review with PR #1.**

Delivered on the recovery branch:
- Durable task-attempt records with worker ID, attempt number, fencing token, heartbeat and lease expiry.
- Atomic leased task claims and heartbeat ownership checks.
- Background heartbeat during Professor execution.
- Atomic persistence of task outcome, evaluation and lease completion.
- Expired attempts are held as recovery_required; no automatic requeue or replay.
- Authenticated inspection and expiry-scan routes.
- Explicit mark_failed and retry decisions with an audit record. Retry requires explicit retry_safe and side_effects_reconciled attestations and never starts automatically.
- Regression coverage for concurrent claims, heartbeat ownership, expiry, restart persistence, recovery decisions and authenticated routes.

Acceptance evidence: latest push and PR workflows each passed 115 tests with one non-blocking Starlette/AnyIO deprecation warning. See PR #1 and docs/task-crash-recovery-phase-1.md.

Remaining Phase 1 limitations: local SQLite only; no distributed worker coordination; recovery actor labels are not verified identity; side-effect reconciliation is caller-attested rather than independently proven.

## Phase 2 — Bounded retries and cancellation

**Status: policy foundation and cooperative cancellation for the bounded local executor implemented; automatic retries remain disabled.**

Design and acceptance matrix: `docs/phase-2-retry-cancellation-design.md`.

Implemented:
- Typed retryable/terminal error classes and a pure fail-closed eligibility evaluator.
- Immutable server-side retry ceilings, finite timing validation, bounded jittered back-off and a frozen capability error-code allowlist.
- Durable, idempotent cancellation requests per task attempt with `requested`, `acknowledged`, `too_late` and `requires_recovery` states.
- Authenticated cancellation request/status routes.
- Fenced cancellation acknowledgement and atomic task/evaluation/attempt persistence.
- Cooperative cancellation checks before execution, after context retrieval, after the local executor returns and before normal completion.
- Expired worker cancellation requests move to operator recovery; completed attempts record late cancellation as `too_late`.
- Failure persistence exceptions return `outcome_unconfirmed` rather than claiming a failed result was durably saved.
- Tests cover retry-policy validation, cancellation idempotency, cancellation/completion races, stale-worker fencing, restart persistence, expired/late requests and API authentication.

Current limits:
- No durable retry schedule or due-work scheduler.
- No registered capability registry or persisted immutable per-attempt retry-policy snapshot.
- No hard execution timeout for uninterruptible work.
- The local executor remains single-attempt; no automatic retry is enabled.
- Cancellation checkpoints are suitable only for the bounded synchronous local executor. Future long-running or external capabilities require their own safe-point and side-effect reconciliation contracts.

At code head `69943ab758155e715baf6d6c4fe96173ce61a04c`, both PR and push workflows passed **171 tests** with one non-blocking Starlette/AnyIO deprecation warning.

Acceptance gates:
- Tests prove retry limits are enforced under concurrent requests.
- Cancellation is deterministic at documented safe points and produces a durable audit event.
- Duplicate execution is prevented by idempotency keys and fencing.
- Non-idempotent or uncertain external actions are never automatically retried.
- Process restart preserves retry/cancellation state.
- Every acceptance-matrix row in the Phase 2 design is covered before Phase 3 begins.

## Phase 3 — Professor capability registry and specialist arms

**Status: planned.**

Deliverables:
- A versioned registry of capabilities with typed input/output schemas.
- Per-capability risk class, permissions/scopes, side-effect declaration, time/resource budgets and approval policy.
- A planner that selects only registered capabilities and validates inputs/outputs.
- Begin with local computation and read-only Source Division research.
- Add specialist arms incrementally: knowledge/research, media, HR/operations and communications drafts.
- Keep email sending, social publishing, payments, trading, purchasing and deletion disabled or approval-gated until later security gates pass.

Acceptance gates:
- Contract tests cover every registered capability and reject malformed inputs or undeclared side effects.
- The orchestrator cannot escalate a capability's scopes or access another arm's credentials.
- Risk classification and human approval are enforced server-side, not just in the UI.
- Capability version and evidence are recorded for every task attempt.

## Phase 4 — Memory and learning governance

**Status: planned.**

Deliverables:
- Separate task context, episodic execution history, source documents and reusable validated lessons.
- Require evidence, provenance and verified reviewer identity before lesson promotion.
- Add review, rejection, correction, supersession and rollback history.
- Scope memory to the correct user or organisation; apply retention and deletion rules.
- Improve retrieval quality only with measurable relevance tests; keep lexical and semantic retrieval claims distinct.
- Treat retrieved content as untrusted data, never as instructions or policy.

Acceptance gates:
- Unapproved, rejected or superseded material cannot enter approved retrieval.
- Every reusable lesson has provenance, validation history and reviewer attribution.
- Tests cover prompt injection, duplicate content, stale sources, conflicting evidence and tenant boundaries.
- A lesson can be corrected or withdrawn without erasing the audit history.

## Phase 5 — Identity, security and release readiness

**Status: planned.**

Deliverables:
- Verified user identity, role-based access control and tenant isolation.
- Per-user/per-tenant delegated credentials with least privilege and a secrets manager.
- Append-only audit events, rate limits, request budgets, monitoring and incident response.
- Tested backup/restore, migration, retention and deletion procedures.
- Threat modelling, dependency/supply-chain review and independent security testing.
- Evidence mapping for UK GDPR, Cyber Essentials, ISO 27001 and SOC 2 readiness where applicable; do not claim certification or compliance without independent evidence.
- A release candidate review with documented rollback and operational ownership.

Acceptance gates:
- Independent security review has no unresolved critical/high findings.
- Tenant isolation, authentication, authorization, audit and data lifecycle tests pass.
- Backups and restore are demonstrated, not merely configured.
- No unapproved external write can occur.
- Separate human approval is obtained before any merge, deployment or production release.

## Immediate next actions

1. Continue the Phase 1 review against the complete PR diff, especially the recovery state machine, authentication dependencies and atomic task/evaluation persistence. Record unresolved findings before changing those paths.
2. Phase 2 design and acceptance-test matrix are committed at `docs/phase-2-retry-cancellation-design.md`.
3. The policy-only foundation is implemented in `atlas_engine/retry_policy.py`: bounded immutable settings, typed errors, a frozen capability error-code allowlist and a pure fail-closed eligibility evaluator. Regression tests live in `tests/test_retry_policy.py`.
4. Next add additive, restart-safe cancellation-request storage and fenced state transitions. Test cancellation-versus-claim races before adding worker checkpoints.
5. Only after durable cancellation and retry-decision records are tested, consider a due-work scheduler. Automatic retries remain disabled; the local executor is not opted into retries.
6. Run both PR and push CI after each meaningful change and record exact branch-head evidence. Do not start Phase 3 implementation until every Phase 2 acceptance gate passes.

## Current project references

- Repository: https://github.com/quickchefbooking-ship-it/Project-atlas-
- Recovery PR #1: https://github.com/quickchefbooking-ship-it/Project-atlas-/pull/1
- Phase 1 design: docs/task-crash-recovery-phase-1.md
- Working branch: atlas/repair-baseline-2026-11-12
- Production/main remains unchanged.
