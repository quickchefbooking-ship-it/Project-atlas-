# Phase 1 — Safe task crash recovery

**Status:** implementation in progress on the existing AtlasOnePro recovery branch. Fenced leases, heartbeats, expiry marking, authenticated inspection routes and explicit recovery decisions are implemented and under CI validation. Distributed recovery and verified operator identity remain out of scope.

## Objective

Detect interrupted task execution and make it recoverable without silently repeating work, losing evaluation evidence, or allowing an old worker to overwrite a newer recovery decision.

## Non-negotiable safety rules

1. A lease timeout is evidence that a worker may be stale; it is not proof that the worker has stopped.
2. Expired work moves to a visible **recovery_required** condition. It is never automatically reset to pending or re-executed.
3. Every execution attempt has a unique attempt ID, worker ID and monotonically increasing fencing token.
4. Heartbeats and completion must match the active attempt and fencing token. A stale worker cannot renew or complete after its lease has been superseded or expired.
5. Task state and its evaluation remain an atomic persistence unit. Recovery must not manufacture a terminal result without an evaluation record.
6. Retrying is permitted only after an explicit recovery decision and after the operation's side-effect safety is known. Future external capabilities must declare idempotency and provide reconciliation for uncertain outcomes.
7. Recovery decisions, lease expiry, heartbeat and attempt transitions are auditable.

## Proposed persistence model

Add a task-attempt/lease record rather than overloading the task's existing status column. The task row remains the high-level summary; the attempt row records who owns execution and when the lease expires.

Minimum attempt fields:
- attempt_id (unique primary key) and task_id (foreign key)
- attempt_number and fencing_token
- worker_id
- state: active, lease_expired, recovery_required, completed, failed, or abandoned
- claimed_at, heartbeat_at, lease_expires_at, finished_at
- Sanitised error_type and recovery metadata where applicable

Use SQLite transactions and conditional updates for claim, heartbeat, expiry marking, recovery decisions and completion. Add indexes for active leases and task history. Existing databases must be upgraded through an idempotent migration; never drop or rewrite existing task/evaluation/lesson data.

## Lifecycle

1. **Claim:** atomically create a new attempt and lease only when the task is pending and no active attempt owns it. Increment attempt number and fencing token in the same transaction.
2. **Heartbeat:** worker periodically extends its lease only when attempt ID, worker ID, fencing token and active state all match.
3. **Expiry detection:** a bounded maintenance operation identifies leases past expiry and marks them recovery_required. It does not requeue the task.
4. **Inspection:** an operator sees task description, attempt history, last heartbeat, elapsed time, capability and whether side effects may have occurred. Do not expose secrets or exception messages.
5. **Recovery decision:** record one of:
   - confirm_completed: only when durable result/evaluation evidence exists and can be reconciled;
   - mark_failed: record a sanitised failure outcome and evaluation atomically;
   - retry: create a new attempt only after confirming no side effect occurred, or proving the operation is idempotent/reconciled;
   - leave_pending_review: retain the recovery hold until evidence is available.
6. **Fencing:** a recovered/superseded attempt cannot heartbeat or commit. Any late completion from an old worker is rejected.

## API and operational surface

Keep the initial recovery interface narrow:
- read-only inspection of stale attempts and task history;
- an explicit, authenticated recovery-decision endpoint;
- no automatic scheduler that retries tasks;
- no public endpoint that bypasses the existing authentication guard.

The shared API key is only a prototype gate, not verified operator identity. Before multi-user/commercial operation, recovery decisions must be restricted to authenticated roles and attributed to a real user.

## Test plan and acceptance gates

- A live lease cannot be claimed by a second worker.
- Heartbeat extends only the matching active lease.
- A wrong worker, wrong attempt ID or stale fencing token cannot heartbeat or complete.
- An expired lease is marked for recovery and is not automatically requeued.
- A task with an expired lease remains non-terminal until a recovery decision is recorded.
- Concurrent expiry/recovery/heartbeat operations preserve one consistent owner and state.
- Recovery retry requires explicit confirmation and rejects unsafe/non-idempotent uncertain work.
- Completion and evaluation remain atomic under injected database failures.
- Existing databases migrate repeatedly without data loss.
- Restart tests prove lease expiry is detected after process restart.
- All failure responses/logs remain sanitised.

## Implementation order

1. Add an idempotent schema migration and attempt/lease storage primitives.
2. Integrate claim and heartbeat with the current TaskAPI while preserving existing task/evaluation invariants.
3. Add stale-attempt inspection and expiry marking, without automatic reclaim.
4. Add explicit recovery decisions with fencing and atomic audit records.
5. Add deterministic fault-injection, concurrency and restart tests; run the full CI suite.

## Implemented in the current prototype slice

- Idempotent task-attempt schema and indexes.
- Atomic leased claim with worker ID and fencing token.
- Heartbeat restricted to the current, unexpired lease owner.
- Expiry scanning marks attempts recovery_required without requeueing tasks.
- Authenticated inspection routes for recovery queue and attempt history.
- Explicit mark_failed decision writes task state, evaluation and decision audit in one transaction.
- Explicit retry requires both retry_safe and side_effects_reconciled confirmations, records the decision, and returns the task to pending without automatically running it.
- TaskAPI now claims a lease, maintains a heartbeat during execution and atomically completes the task, evaluation and lease.

## Explicitly out of scope for Phase 1

- Distributed worker queues or multi-host consensus.
- Automatic task retries or automatic recovery.
- Replaying arbitrary tasks after a crash.
- Executing untrusted proposal code.
- External write capabilities such as sending, publishing, payments or trading.
- Merging the recovery PR or deploying to production.
