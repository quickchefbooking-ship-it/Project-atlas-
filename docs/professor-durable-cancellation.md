# Professor durable cancellation signal

**Status: durable tenant-scoped cancellation is connected to the bounded HTTP plan executor. A separate persistent worker is not yet implemented.**

The cancellation repository records an immutable stop request for a tenant plan. The tenant execution API exposes `POST /professor/tenant/plans/{plan_id}/cancel` and the one-step executor observes the signal at safe dispatch boundaries.

## Guarantees

- Only an active tenant principal with `plans:write` can request cancellation.
- Only plans in `ready` or `running` state accept a request.
- The first request wins; repeated requests are idempotent and cannot overwrite the original requester or reason.
- Only a principal with `steps:read` can inspect the stop signal.
- Cross-tenant requests and reads are denied without disclosing another tenant's plan.
- Cancellation records cannot be updated or deleted.
- The step-claim transaction checks the cancellation table before creating or claiming work, closing the race between the HTTP preflight and a concurrent cancellation request.
- The plan repository refuses a transition to `succeeded` when a cancellation request has committed. The cancellation request and terminal-success transition serialize through SQLite write transactions.
- If a step is already claimed, it may finish its bounded handler call. The executor then records that step's actual outcome and transitions the plan to `cancelled`; no subsequent step is claimed.
- If an uncertain lease has expired, cancellation does not replay it. The response preserves the recovery-required state and calls for operator review.

## HTTP behavior

- `POST /professor/tenant/plans/{plan_id}/cancel` accepts a bounded JSON reason and returns `cancellation_requested`.
- `POST /professor/tenant/plans/{plan_id}/execute-next` returns `cancelled` when no step is active, or `cancellation_requested` while an already-claimed step is still finishing.
- The global capability kill switch remains in force for execution. The cancellation endpoint remains available so an operator can request a stop even when execution is disabled.

## Remaining worker work

This is graceful plan cancellation for the existing request-scoped executor, not a dedicated persistent worker or OS sandbox. A separate worker still needs:
1. its own supervised process lifecycle and trusted workload identity;
2. bounded lease heartbeat and shutdown handling;
3. cancellation checks at handler-supported safe checkpoints for longer-running work;
4. an OS-enforced sandbox and network egress policy before arbitrary build/test commands are allowed;
5. explicit recovery and operator controls for uncertain work.

No production worker is enabled. No external side effects, secrets, payment configuration, production data, merge or deployment are changed by this implementation.
