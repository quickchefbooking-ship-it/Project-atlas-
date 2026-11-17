# Professor durable cancellation signal

**Status: implemented as a tenant-scoped persistence primitive; worker integration is pending.**

The cancellation repository adds an immutable, durable stop request for a tenant plan. It is designed for a future independently supervised worker to check before claiming a step, before handler dispatch, at safe checkpoints and before committing completion.

## Guarantees

- Only an active tenant principal with `plans:write` can request cancellation.
- Only plans in `ready` or `running` state accept a request.
- The first request wins; repeated requests are idempotent and cannot overwrite the original requester or reason.
- Only a principal with `steps:read` can inspect the stop signal.
- Cross-tenant requests and reads are denied without disclosing another tenant's plan.
- Cancellation records cannot be updated or deleted.
- No worker is started, no in-flight handler is interrupted by this persistence layer, and no plan or step state is silently rewritten.

## Worker integration still required

The worker runner must consult this repository:
1. before claiming work;
2. immediately after claiming and before input mapping;
3. immediately before handler invocation;
4. at handler-supported safe checkpoints;
5. before persisting a successful outcome.

If cancellation is observed, the runner must stop safely and ensure the lease/fencing rules prevent stale completion. The runner must not automatically retry uncertain work. This change is a durable signal only, not a complete cancellation mechanism.
