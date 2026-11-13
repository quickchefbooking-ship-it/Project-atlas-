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

**Status: initial policy primitives implemented; durable scheduling and cancellation remain.**

Design and acceptance matrix: `docs/phase-2-retry-cancellation-design.md`. Added `atlas_engine/retry_policy.py` with typed retryable/terminal errors, immutable server-side limits, a pure fail-closed eligibility evaluator and bounded jittered back-off calculation. Added regression coverage for default no-retry, error classification, capability idempotency, max attempts, deadline, jitter and invalid policy values. Both PR and push workflows passed 144 tests on head `a72af1ab2fe5f28aacde341f68c3651e534a7561`. This code does not schedule or execute retries.

Deliverables:
- Define retryable versus terminal error classes; do not retry validation, permission or policy failures.
- Add configurable attempt ceilings, timeouts and bounded exponential back-off with jitter.
- Require capability-level idempotency declarations before automatic retry is eligible.
- Persist retry scheduling, attempt outcomes and cancellation requests.
- Add cooperative cancellation checkpoints and safe shutdown semantics; never kill a worker mid-write without reconciliation.
- Ensure an operator can inspect, pause, cancel or resume eligible work.

Acceptance gates:
- Tests prove retry limits are enforced under concurrent requests.
- Cancellation is deterministic at documented safe points and produces a durable audit event.
- Duplicate execution is prevented by idempotency keys and fencing.
- Non-idempotent or uncertain external actions are never automatically retried.
- Process restart preserves retry/cancellation state.

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
