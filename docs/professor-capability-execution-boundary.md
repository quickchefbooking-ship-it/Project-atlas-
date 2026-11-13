# Professor capability execution boundary — design and acceptance gates

**Status:** design only. This document does not add a handler runner, enable capability execution, grant permissions, connect external services or change production behaviour.

## 1. Purpose

The capability registry now has a draft implementation of strict input/output contract validation. That is necessary but not sufficient to execute a specialist arm safely. Before any handler can run, Professor needs a separately enforced execution boundary that binds a specific caller, tenant, task, attempt, capability version, approved parameters and resource budget into one auditable decision.

The default state remains **execution disabled**. A capability being registered, schema-valid, discoverable or proposed by a plan does not authorise it to run.

## 2. Non-goals

This phase must not:
- invoke handlers or add a generic plugin runner;
- execute arbitrary Python, shell commands, generated code or user-supplied modules;
- add live email, messaging, social, payment, trading, purchasing or publishing actions;
- treat caller-supplied actor labels, a shared API key, a plan, or a schema-valid payload as identity or approval;
- add credentials to task context, prompts, logs or capability definitions;
- introduce autonomous retries or background dispatch;
- migrate production data, merge a pull request or deploy.

## 3. Required execution envelope

A future execution request must be represented by a server-created, immutable envelope. At minimum it binds:

| Field | Requirement |
| --- | --- |
| request_id | Unique, unpredictable request identifier |
| tenant_id | Derived from verified authentication context, never accepted from task payload |
| principal_id | Verified subject from the identity provider |
| granted_scopes | Server-resolved, capability-specific scopes |
| task_id | Existing persisted task |
| attempt_id | Current durable task attempt |
| fencing_token | Current attempt ownership token |
| capability_name / version | Exact registered capability identity |
| input_digest | Hash of canonical validated input; do not log raw sensitive input |
| approval_id | Required for actions whose policy requires human approval |
| issued_at / expires_at | Short validity window, checked at dispatch |
| trace_id | Correlates policy decision, execution and audit events |

The envelope is created only after authentication, tenant resolution, scope evaluation, task/attempt ownership verification, risk classification, schema validation and approval checks. Callers must not be able to construct or modify trusted envelope fields.

## 4. Policy decision sequence

The execution gate must fail closed and apply checks in this order:

1. **Global kill switch:** execution disabled means reject every invocation before handler lookup.
2. **Verified identity:** reject missing, expired or unverifiable authentication. Display names and actor labels are not identity.
3. **Tenant boundary:** resolve tenant membership server-side and verify the task belongs to that tenant. Reject cross-tenant references without revealing whether another tenant's object exists.
4. **Capability allowlist:** require an application-owned registered capability and exact version. Task input, plans and external content cannot register or alter capabilities.
5. **Scope check:** require every declared scope and reject unknown or broader-than-granted scopes.
6. **Task ownership:** verify task, attempt, lease and fencing token are current and consistent.
7. **Risk policy:** read-only/local computation may be eligible for later controlled execution; external writes and privileged actions remain denied unless a separate policy and explicit action-bound approval are present.
8. **Approval binding:** where required, approval must bind the exact capability version, target, canonical parameters/input digest, principal, tenant, expiry and one-time use. A generic “yes” or approval of a plan is insufficient.
9. **Input contract:** run the pinned JSON Schema validator and payload bounds immediately before dispatch.
10. **Resource policy:** enforce capability-specific wall-clock deadline, CPU/memory/output limits and concurrency quotas outside the handler's trust boundary.
11. **Audit reservation:** persist a durable “authorised/dispatching” event before any handler side effect can begin.
12. **Dispatch:** only a fixed, application-owned handler binding may be called. No dynamic import, eval, shell or user-selected callable.
13. **Output contract:** validate and bound the returned JSON object before it can be persisted or passed to another arm.
14. **Final audit:** persist terminal outcome, timing, resource usage, output digest and any error category. Never store secrets or raw sensitive payloads in ordinary logs.

Any failed check must produce a stable denial code and no handler invocation.

## 5. Handler isolation and resource controls

A Python timeout around a thread is not a safe cancellation mechanism: it cannot reliably stop the underlying work or undo a side effect. The first executable implementation, if later approved, should therefore support only pure, bounded local functions in-process, with no network, filesystem writes, credentials or arbitrary code execution.

Any capability that needs network access, filesystem access, a third-party SDK, credentials or an external side effect must run in a separately isolated worker/container with:
- a deny-by-default network policy and explicit destination allowlist;
- a dedicated, least-privilege identity or delegated credential scoped to that one capability;
- read-only filesystem by default and a per-invocation scratch directory where needed;
- hard process/container CPU, memory, output-size and wall-clock limits;
- process termination that is effective even if the handler ignores cancellation;
- no host Docker socket, host filesystem mounts, inherited environment secrets or access to other arms' credentials.

If those controls are not available, the capability is not executable.

## 6. Approval and side-effect semantics

The following remain categorically unavailable to the initial local execution pilot: trading, money movement, purchases, payment capture/refunds, outbound email or messages, social publishing, deletion, permission changes, production deployment and account/security changes.

A future approval record must be single-use and atomically consumed. It must be invalidated if any bound parameter, target, capability version, tenant, principal or expiry changes. Replays must be rejected. Retries must not reuse an approval unless the approval policy explicitly authorises an idempotent retry and reconciliation is proven.

A timeout or worker crash after dispatch is an **unknown outcome**, not proof of failure. The task must enter recovery-required; do not blindly replay a possible external side effect.

## 7. Audit model

Record append-only events for:
- policy evaluation requested and its decision;
- each denial reason;
- approval created, presented, consumed, expired or rejected;
- dispatch started and completed/failed/timed-out;
- output validation result;
- recovery or reconciliation decision.

Each event should include tenant, verified principal, task, attempt, fencing token, capability identity/version, trace ID, timestamp and relevant digests. Do not log API keys, bearer tokens, credentials, raw personal data or complete sensitive payloads. Audit writes must be transactionally tied to the state transition they describe where possible. If the audit reservation cannot be persisted, do not dispatch.

## 8. Minimum test matrix before any runtime is enabled

Tests must prove at least:

- global execution switch defaults off and denies every capability;
- missing/invalid identity, expired sessions and revoked membership deny execution;
- tenant A cannot inspect or execute tenant B's task/capability/approval;
- caller-supplied tenant, principal, scope or approval fields are ignored/rejected;
- unknown capability and stale capability version are denied;
- insufficient, unknown or escalated scopes are denied;
- stale attempt, expired lease and incorrect fencing token are denied;
- unapproved external-write and privileged capabilities are denied;
- approval mismatch, expiry, replay and concurrent double-consumption are denied;
- schema-invalid, non-JSON, non-finite and oversized inputs never reach a handler;
- handler output is bounded and schema-validated before persistence;
- resource exhaustion and ignored cancellation terminate the isolated worker;
- audit reservation failure prevents dispatch;
- crash before dispatch is safely retryable; crash after dispatch is recovery-required;
- duplicate requests cannot invoke the same non-idempotent action twice;
- secrets and sensitive values do not appear in API errors, logs or audit metadata.

Use fake handlers and deterministic test identities only. Tests must assert handler call count is zero for every denied case.

## 9. Staged implementation plan

**Stage A — contracts and policy model (design only):** agree the envelope, denial codes, scope semantics, approval binding and audit event schema. No handlers.

**Stage B — pure local pilot:** only after verified identity and tenant isolation exist, implement a disabled-by-default dispatcher for one application-owned, pure local capability. Use fake identity provider fixtures and no external I/O.

**Stage C — isolated worker:** prove process/container isolation, quotas, termination, network denial and secret separation before adding any capability that accesses external resources.

**Stage D — one read-only specialist adapter:** add one source adapter with explicit delegated read-only scopes, provenance and contract tests. Keep all write actions unavailable.

**Stage E — separately reviewed write capabilities:** each external-write capability requires its own threat model, approval semantics, idempotency/reconciliation plan and explicit product-owner approval. No blanket enablement.

A stage is not complete because code exists. It requires passing CI on the exact commit, documented test evidence, security review and an explicit acceptance decision.

## 10. Current gate and status

- PR #8 adds strict capability schema validation but does not invoke handlers.
- PR #8 CI passed on exact head `92e6d1646844dd22aa5fb577058202a5e395f43f` (GitHub Actions run 43484841655).
- Verified identity, role/scope enforcement, tenant isolation, action-bound approval and isolated workers are not yet implemented.
- Therefore capability execution remains disabled. This document is a proposal for review, not an assertion that the controls exist.
