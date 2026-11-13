# Phase 2 — Bounded retries and cooperative cancellation

**Status: design and acceptance contract. No runtime retry or cancellation behaviour is enabled by this document.**

## Goals and non-goals

Phase 2 adds durable controls around task execution without weakening Phase 1's lease, fencing, and atomic task/evaluation guarantees. A retry is a new, separately recorded attempt; it is never an in-place replay of a running attempt.

This phase does not add distributed scheduling, multi-host coordination, arbitrary code execution, external write integrations, or automatic retry of uncertain side effects. SQLite remains a single-host prototype boundary. No task is retried automatically merely because a worker disappeared.

## Safety invariants

1. **Default to no retry.** Existing tasks and executors retain one execution attempt unless a policy explicitly opts in.
2. **Capability opt-in is mandatory.** Automatic retry requires a registered capability contract that declares itself idempotent, defines its idempotency-key scope, and has no undeclared side effects. A task description or caller-supplied boolean is not a capability contract.
3. **Fail closed.** Unknown exceptions, validation errors, permission/authentication failures, policy denials, malformed inputs, and persistence errors are terminal or recovery-required; never classify them as retryable by default.
4. **Only known transient failures may retry.** A capability may map a narrow, documented exception set to retryable failures. The classifier must not infer retryability from message text. The capability contract must retain a verifiable test-evidence reference; a boolean claim alone is insufficient.
5. **Bound every dimension.** Enforce a hard maximum attempt count, per-attempt execution timeout, total task deadline, maximum back-off, and bounded jitter. Configuration is validated and capped server-side.
6. **No retry while an earlier attempt is uncertain.** Expired leases remain `recovery_required`. A retry can be scheduled only after the old attempt is terminal/reconciled and the idempotency contract guarantees duplicate suppression.
7. **Fence all state changes.** Heartbeats, cancellation acknowledgements, retry scheduling, and completion must match the current attempt ID, worker ID and fencing token. A stale worker cannot complete or overwrite a newer attempt.
8. **Cancellation is cooperative.** Persist a cancellation request; workers observe it at documented safe points. Never kill a worker in the middle of a side effect or database transaction.
9. **Cancellation wins before a new attempt starts.** A task with a pending cancellation request cannot be claimed for another attempt. A race between claim and cancellation is resolved transactionally.
10. **Audit durable decisions.** Record who/what requested cancellation, when it was requested/acknowledged, why a retry was scheduled or refused, and the policy/capability version used. Current caller-supplied actor labels are not verified identity and must remain labelled as such.
11. **Keep outcomes atomic.** Terminal task status, evaluation, attempt finalisation and relevant audit event are committed together where they share the SQLite database. Persistence failure returns an unconfirmed/recovery-required outcome, never a fabricated terminal result.
12. **No external writes.** Email, publishing, payments, trading, purchasing, deletion and other external side effects remain disabled or human-approval gated. Phase 2 does not enable them.

## Error classification contract

| Class | Examples | Retry behaviour |
|---|---|---|
| `RetryableExecutionError` | Explicitly declared transient provider/network/service-unavailable failure from an opted-in idempotent capability | Eligible only within all policy, attempt, deadline and idempotency gates |
| `TerminalExecutionError` | Unsupported operation, invalid task, validation failure, permission/policy failure, deterministic business rejection | Never retry automatically |
| Unknown exception | Any exception not explicitly classified by the capability | Terminal by default; sanitised error type only in public response |
| Lease/fencing loss | Heartbeat rejected, stale token, expired lease | Stop work at safe point; mark/retain recovery-required; never self-retry |
| Persistence failure | Failure to atomically commit task/evaluation/attempt/audit | Outcome unconfirmed; operator recovery required; never retry execution automatically |
| Cancellation | Durable cancellation request observed at a safe point | Stop before next safe unit; record cancelled outcome; do not retry |

The existing local arithmetic executor is deterministic and has no declared transient failure class. Its default retry count therefore remains one. A failed success-criteria evaluation is a completed execution with a failed evaluation, not a transient execution error.

## Retry policy contract

A policy is immutable for an attempt and records its version in the attempt/audit data. Initial prototype defaults:

- `max_attempts = 1` globally until a capability explicitly opts in.
- Hard ceiling for any future opt-in: 3 total attempts (initial attempt included).
- Per-attempt timeout: 30 seconds by default, configurable only downward within a server-enforced ceiling.
- Total task deadline: 90 seconds by default, never extended by retries.
- Exponential back-off: `min(base_delay * 2^(attempt_number - 1), max_delay)`.
- Initial base delay: 1 second; maximum delay: 15 seconds.
- Jitter: bounded full jitter in `[0, calculated_delay]`; persist the selected `next_run_at` so restart does not recalculate or accelerate it.
- Do not sleep inside a request handler or worker thread to wait for a retry. Persist a scheduled state and let a later scheduler/claim operation consider it when due.
- No retry after total deadline, max attempts, cancellation request, terminal error, lease uncertainty, or failed side-effect reconciliation.

These are prototype caps, not performance claims. They must be configurable through validated server-side settings, not arbitrary per-request overrides.

## Idempotency contract

Before a capability may opt into automatic retry it must declare:

- stable capability name and version;
- input schema and canonical input hashing rules;
- idempotency key derivation and uniqueness scope;
- whether the capability is read-only or has side effects;
- the system that enforces duplicate suppression and the retention period for keys;
- what evidence proves a previous operation completed or did not occur;
- retryable exception types and any operation-specific reconciliation steps.

A local task key can prevent duplicate local task/attempt creation but cannot by itself make an external provider operation idempotent. If the provider does not enforce a key or offer reliable reconciliation, automatic retry is prohibited.

## Cancellation state contract

Persist cancellation as a request separate from the task's execution status. Suggested states:

- `none`: no request;
- `requested`: durable request waiting for worker observation;
- `acknowledged`: worker reached a safe point and stopped;
- `too_late`: task already committed a terminal outcome;
- `requires_recovery`: worker/lease was lost before cancellation could be confirmed.

Safe points are before execution starts, between bounded local computation units, before an external call, and after an external call has returned but before committing its result. No external calls are enabled in this phase. A worker that loses its lease must not acknowledge cancellation as successful unless it still owns the current fencing token.

## Persistence model to validate before implementation

Prefer additive SQLite migrations, preserving all Phase 1 tables and APIs:

- extend attempt records with immutable policy/capability version, classified error code, scheduled retry time, start/deadline/finish times and cancellation observation;
- add a task cancellation request/audit table with unique request identity and state transitions;
- add a durable retry schedule containing the originating attempt, next attempt number, due/deadline timestamps, capability name/version, idempotency key and immutable policy snapshot;
- add indexes for due scheduled work and unresolved cancellation requests.

Every transition must be conditional on the current state and fencing token. Migration must be idempotent and restart-safe. Do not delete historical attempt or decision records.

## Implementation sequence

1. Add typed error classes and a pure retry-policy evaluator; default unknown/legacy executors to no retry.
2. Add capability retry declarations as an internal contract; do not yet expose user-controlled capability registration.
3. Add additive storage migrations and unit tests for due scheduling, attempt ceilings, immutable policy snapshots and concurrent claims.
4. Add cancellation persistence and conditional state transitions; test cancellation/claim races and stale-worker rejection.
5. Add cooperative cancellation checks and hard timeout handling for the local executor only. A timeout must not falsely imply that an uninterruptible side effect was rolled back.
6. Add the scheduler/claim path for due retries without sleeping in request handlers. If no safe scheduler exists, leave retries manually claimable and disabled by default.
7. Run the full test suite and both PR/push CI workflows. Review the diff for accidental changes to main, production configuration, secrets or external integrations.

## Acceptance-test matrix

| Area | Required test evidence |
|---|---|
| Classification | Retryable only for explicitly declared exception types; validation, auth, permission, policy, unknown and persistence errors never retry |
| Default compatibility | Existing local executor and legacy tasks execute at most once |
| Attempt ceiling | No more than configured attempts, including under concurrent claims and repeated scheduler scans |
| Back-off | Formula, cap, jitter bounds, immutable policy snapshot and persisted due time/deadline are validated; claims cannot start early or after expiry |
| Deadline/timeout | The bounded local executor checks a monotonic per-attempt deadline during AST evaluation, rejects over-complex expressions, and returns a sanitised timeout failure; no claim of hard termination for uninterruptible code |
| Idempotency | Missing/invalid capability declaration or missing test-evidence reference blocks retry; duplicate idempotency key cannot cause a second side effect in the fake provider |
| Recovery | Expired lease remains held; no retry until prior outcome is reconciled; stale fencing token cannot schedule or complete |
| Cancellation | Request persists across restart; worker acknowledges at a safe point; claim/cancel race has one deterministic winner |
| Cancellation safety | Cancelled task or scheduled retry is terminalised and not re-claimed; too-late and requires-recovery states are distinguishable |
| Audit/atomicity | Retry/cancel decisions survive restart; failed transaction leaves no partial terminal state or audit record |
| API security | New routes require existing API-key dependency; no sensitive exception text or secrets in responses/logs |
| Regression | All Phase 1 tests remain green; no change to main, production, paid providers or external write integrations |

## Prototype implementation status

The initial policy-only foundation is implemented in `atlas_engine/retry_policy.py` and covered by `tests/test_retry_policy.py`:

- `RetryPolicy` enforces server-side ceilings and finite numeric settings.
- `RetryableExecutionError` accepts only bounded, explicit error-code identifiers.
- `CapabilityRetryContract` requires actual boolean declarations and freezes the error-code allowlist into a `frozenset`, so a caller cannot mutate an already-validated contract.
- `evaluate_retry` requires a positive integer attempt number and fails closed for unknown errors, invalid capability objects, cancellation, lease uncertainty and persistence failure.
- The evaluator computes a bounded delay only; it does not sleep, schedule, claim or execute another attempt.

Retry scheduling now has durable, fenced storage primitives, but is not enabled for the existing executor:

- SQLite stores a retry schedule only when a trusted internal caller supplies a capability contract with explicit idempotency, declared side effects, verified duplicate suppression, an allowlisted transient error code and a non-empty test-evidence reference.
- Scheduling atomically finalises the failed attempt, persists its evaluation, returns the task to pending and stores a policy snapshot, idempotency key, next-attempt number, due time and hard deadline.
- Claims are blocked before due time, after the deadline, after schedule cancellation/expiry, or when the next attempt number does not match. A due claim atomically consumes the schedule and links it to the new fenced attempt.
- Expired schedules become `expired` and atomically terminalise the pending task with an evaluation; they are not silently requeued. A cancellation request against a pending scheduled retry cancels the schedule and terminalises the task with a cancellation evaluation so it cannot be claimed or left pending.
- An authenticated read-only `GET /tasks/{task_id}/retry-schedules` endpoint exposes schedule history; there is no public schedule-creation endpoint and no current executor invokes retry scheduling. There is no unattended scheduler or registered capability registry, so default behaviour remains one attempt.

Cancellation is now a durable, cooperative runtime path for the current synchronous local executor:

- SQLite stores one idempotent cancellation request per task attempt, with `requested`, `acknowledged`, `too_late` and `requires_recovery` states.
- Authenticated `POST /tasks/{task_id}/cancel` and `GET /tasks/{task_id}/cancellation` routes expose request and status operations. Actor labels are caller-supplied audit metadata, not verified identity.
- The worker checks for a request before execution, after bounded context retrieval, after the local executor returns, and before normal completion. It does not kill synchronous work mid-operation.
- The bounded local executor receives a 30-second monotonic per-attempt deadline, checks it around parsing and during AST evaluation, and caps AST complexity at 128 nodes. This is cooperative for the local arithmetic executor, not a hard kill for uninterruptible code or future external capabilities.
- A requested cancellation blocks normal task/evaluation completion. Acknowledgement is fenced by attempt ID, worker ID, fencing token and live lease, and atomically records the cancellation evaluation and task/attempt outcome.
- Expired worker leases move pending cancellation requests to `requires_recovery`; a late request against a completed/terminal attempt is recorded as `too_late`.
- The API reports `cancelled`; the current task schema records its terminal task status as `failed` with `TaskCancelled`, and the evaluation method as `cancelled`. This preserves the existing task status constraint without a destructive schema migration.

This is not yet an unattended runtime retry system. Durable schedule persistence and due-time claim gates exist, but there is no registered capability registry, scheduler that discovers and dispatches due work, or per-attempt hard timeout. The capability evidence value is a caller-supplied reference string, not independently verified by the runtime; it must not be treated as proof until a trusted registry and reviewable evidence-verification process exist. The default retry policy remains one attempt, and the local executor is not opted in. The current cancellation checkpoints are appropriate only for the bounded synchronous local executor; future long-running or external capabilities need their own safe-point and side-effect reconciliation contracts.

## Exit gate

Phase 2 is complete only when all matrix rows have passing automated tests, both GitHub Actions paths are green on the same branch head, and the PR records exact evidence. Passing tests do not authorise merge, deployment or production release.
