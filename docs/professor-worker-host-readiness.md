# Professor worker host readiness gate

**Status: preflight specification only.** This change does not start a worker, provision infrastructure, enable execution, or change deployment settings.

## Cost and deployment guard

The first implementation must use existing project infrastructure and free/open-source components wherever practical. No new paid service, compute instance, managed queue, storage tier, domain, or subscription may be provisioned as part of this work.

- Preserve the owner's existing £20 billing ceiling as a hard maximum, not a spending target.
- Target incremental spend: £0.
- Any unavoidable charge, plan upgrade, paid add-on, or usage-based service requires explicit owner approval before activation.
- Do not infer that a Replit deployment supports privileged containers, a Docker socket, nested OCI runtimes, or a persistent background process. Verify the actual deployment/runtime capability and plan limits first.
- Do not move production data or credentials to a new host during preflight.

## Host decision sequence

1. **Inspect the existing deployment.** Record the current host, runtime, process model, filesystem persistence, restart behaviour, available CPU/RAM/disk limits, outbound network policy, and whether a separately supervised process is supported.
2. **Check for a safe existing execution environment.** Prefer an already available Linux host or isolated runner that can run a non-root OCI workload without additional spend. A normal web process, temporary directory, or application container alone is not proof of a security boundary.
3. **Prove isolation before enabling execution.** The environment must support a pinned image, non-root UID, read-only base filesystem, dedicated disposable workspace, no host/Docker socket/production mounts, no cloud metadata access, network disabled by default, hard CPU/memory/PID/disk/time limits, and reliable process termination/cleanup.
4. **Keep the web application separate.** The AtlasOnePro web service remains the control plane. The worker receives only a narrowly scoped workload identity and tenant grants; it must not inherit web-session cookies, provider keys, deployment secrets, or broad application credentials.
5. **If any gate fails, stop.** Continue with offline unit tests and a disabled worker interface. Do not emulate isolation with a temporary folder, do not run repository scripts or shell commands in the web process, and do not buy infrastructure automatically.

## Required runtime configuration

All settings are deployment-owned and validated at process startup. Missing, malformed, or contradictory values fail closed.

- Global capability execution switch: disabled unless explicitly enabled by an owner-controlled deployment change.
- Dedicated Professor worker enablement: disabled by default.
- Server-assigned worker ID: required and bounded.
- Explicit tenant grants: required; no wildcard tenant, no browser-supplied tenant, no wildcard scopes.
- Autonomy mode: fixed by trusted deployment configuration; worker cannot promote itself.
- Isolation backend: required and positively verified before any untrusted build/test activity.
- Capability allowlist: first slice is deterministic local computation only; networked research and arbitrary code execution remain excluded.
- Resource budget: explicit bounded lease, wall-clock, CPU, memory, process and result-size limits.
- Shutdown: drain new claims, stop dispatch, revoke/expire leases safely, terminate active process groups and clean disposable workspaces.

## First execution slice

The first live worker slice may claim one already-approved, tenant-scoped step at a time and invoke only a fixed application-owned deterministic local-computation handler. It must reuse the existing plan, step lease, cancellation, identity, capability registry, autonomy policy and append-only audit repositories.

Before dispatch it must re-check, in order:

1. global kill switch and worker enablement;
2. worker identity and exact tenant grant;
3. plan state, approval and dependency readiness;
4. registered capability name, version and schema;
5. exact step scopes and autonomy action;
6. cancellation request;
7. live lease and fencing token;
8. durable audit reservation.

After execution it must re-check cancellation and lease/fencing ownership before recording a bounded result and append-only outcome. A lost lease, expired lease, cancellation, missing audit reservation, or failed check prevents success. Expired work remains `recovery_required`; never automatically replay uncertain work.

## Acceptance evidence before activation

- Host capability report with plan/usage limits and confirmation of no incremental cost.
- Isolation proof from the actual deployment environment, including negative tests for host filesystem, Docker socket, metadata endpoint and network access.
- Tests for disabled-by-default, global stop, tenant isolation, missing grants, unknown capability, policy denial, cancellation, stale fencing token, audit-before-dispatch, timeout, bounded output and cleanup.
- A draft-only change with exact-head CI green and reviewable test evidence.
- Separate owner approval for any deployment enablement. No autonomous merge, production deployment, secret modification, authorization change, production write, live payment or external message.

## Current decision

Until the host capability report and isolation proof exist, the worker remains **not runnable**. The safe deliverable is the tested worker contract and preflight evidence, not a pretend background process. This is an intentional security gate, not a blocker to continued offline development.
