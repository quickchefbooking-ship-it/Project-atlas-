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

**Status: policy foundation, durable cancellation and retry-schedule primitives implemented; unattended retries remain disabled.**

Design and acceptance matrix: `docs/phase-2-retry-cancellation-design.md`.

Implemented:
- Typed retryable/terminal error classes and a pure fail-closed eligibility evaluator.
- Immutable server-side retry ceilings, finite timing validation, bounded jittered back-off and a frozen capability error-code allowlist.
- Capability contracts require explicit boolean safety declarations and a non-empty test-evidence reference before they are considered retry-safe.
- Durable, idempotent cancellation requests per task attempt, with requested, acknowledged, too_late and requires_recovery states.
- Authenticated cancellation request/status routes.
- Fenced cancellation acknowledgement and atomic task/evaluation/attempt persistence.
- Cooperative cancellation checks before execution, after context retrieval, after the local executor returns and before normal completion.
- Expired worker cancellation requests move to operator recovery; completed attempts record late cancellation as too_late.
- Durable retry schedules store originating attempt, next attempt number, due/deadline timestamps, capability name/version, idempotency key, capability evidence and immutable policy snapshot.
- Retry scheduling atomically finalises the failed attempt and evaluation, returns the task to pending and persists the schedule.
- Claims cannot start before due time, after the deadline, beyond the configured attempt ceiling, or after schedule cancellation/expiry. Due claims consume the schedule and link it to a new fenced attempt atomically.
- A cancellation request against a pending scheduled retry cancels and terminalises the task with an evaluation. An expired retry deadline also terminalises the task with a retry-expired evaluation.
- Tests cover retry policy validation, capability evidence, fake-provider duplicate suppression, cancellation idempotency/races/fencing, restart persistence, expired/late requests, retry schedule eligibility, due-time gating, concurrent claims, attempt ceilings, expiry, terminal outcomes and scheduled-retry cancellation.

Current limits:
- No registered capability registry or scheduler that automatically discovers and dispatches due work.
- No per-attempt hard timeout for uninterruptible work.
- The existing local executor remains single-attempt and is not opted in; retry scheduling is an internal primitive only.
- Cancellation checkpoints are suitable only for the bounded synchronous local executor. Future long-running or external capabilities require their own safe-point and side-effect reconciliation contracts.
- Shared API-key authentication and caller-supplied actor labels are not verified per-user identity or RBAC.

At code head `e140bc0c15dfcf7f3fb98375e913eca908cbbcff`, both PR and push workflows passed **184 tests** with one non-blocking Starlette/AnyIO deprecation warning.

Acceptance gates:
- Tests prove retry limits are enforced under concurrent requests and due-time claims.
- Cancellation is deterministic at documented safe points and produces a durable audit event.
- Duplicate execution is prevented by idempotency keys and fencing for any future opted-in capability.
- Non-idempotent or uncertain external actions are never automatically retried.
- Process restart preserves retry/cancellation state and immutable schedule snapshots.
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

1. Complete a focused review of the Phase 1/2 combined diff, especially cancellation-versus-completion ordering, expired lease recovery, and the task/evaluation/attempt transaction boundaries.
2. Keep the current shared API-key limitation explicit: actor labels are not verified identity, and this prototype is not suitable for public multi-user use.
3. Add a registered, versioned capability registry and immutable per-attempt policy snapshots before any runtime retry scheduling is considered.
4. Add durable retry-decision and due-time records with restart/concurrency tests, but leave the scheduler and automatic retries disabled until idempotency and reconciliation evidence are independently enforceable.
5. Revisit per-attempt timeout semantics only with an executor that can stop safely or prove side-effect reconciliation; do not imply a thread timeout can undo work.
6. Run both PR and push CI after each meaningful change and record exact branch-head evidence. Do not start Phase 3 until every Phase 2 acceptance gate passes.

## Current project references

- Repository: https://github.com/quickchefbooking-ship-it/Project-atlas-
- Recovery PR #1: https://github.com/quickchefbooking-ship-it/Project-atlas-/pull/1
- Phase 1 design: docs/task-crash-recovery-phase-1.md
- Working branch: atlas/repair-baseline-2026-11-12
- Production/main remains unchanged.
