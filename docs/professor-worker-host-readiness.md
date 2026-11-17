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


## Initial ATLAS Replit host inspection — 17 November 2026

A read-only inspection of the user's existing Replit app named **ATLAS** found the following. No packages were installed, no containers or workers were started, no deployment settings or secrets were changed, and no cost was incurred.

### Verified in the inspected project/workspace

- The app is configured for an **Autoscale** deployment. Replit's documented Autoscale behaviour permits scale-to-zero; this is not a guarantee of a continuously running worker.
- The existing Brain queue worker is started as an asyncio task inside the API application's lifespan. It is not a separately supervised production service.
- The scheduled learning runner is explicitly reported as not configured.
- The development workspace has Docker CLI and an accessible Docker socket; a read-only Docker information check succeeded. No containers were started, listed or created.
- The development workspace reports 4 CPUs and an 8 GiB memory cgroup limit. These are workspace observations, not published Autoscale resource guarantees.
- Replit documentation says published deployment filesystems are ephemeral/reset on republish. The inspected API deployment config did not establish a persistent volume or external database for the SQLite fallback.
- The production deployment's access to Docker, privileged OCI execution, CPU/RAM sizing, persistent background processes and account-specific billing limits remains unknown.

### Decision from this inspection

**Do not run the Professor worker inside the current Autoscale API process.** It could stop when the service scales down, and the development Docker socket does not prove a production isolation boundary. A Reserved VM or another always-on host may support continuous execution, but its cost and suitability are not established and must not be selected automatically.

Continue with disabled-by-default worker contracts and offline tests. Before any live worker, obtain deployment-specific evidence for an isolated non-root container runtime, durable queue/database storage, bounded resources, shutdown/cleanup, and a cost estimate showing £0 incremental spend. If the existing Replit plan cannot satisfy these requirements for £0, stop and present the options for explicit owner approval.

### Source-revision reconciliation required

The Replit inspection reported the ATLAS workspace on `main` at `2f182eaa87ee4ecab41e26963b1ff5b9050387d8`. The connected GitHub repository's default `main` ref was independently observed at `32471ea720edb5f10ca51aafaf9d45113d4e736c` during this work. These are different commit IDs. Confirm that the Replit app is linked to the intended authoritative repository and branch before assuming a GitHub draft PR is reflected in the running app. No deployment URL or successful build metadata proves that the currently served app contains either commit.


## Implementation checkpoint — one-step coordinator

The draft now includes `atlas_engine/professor_worker_runner.py` and focused tests. This is a **coordinator contract**, not a background process or isolation backend.

- A tick handles at most one step and never loops or retries.
- It requires three independent trusted gates: worker enabled, global execution enabled, and isolation verified. All default to false.
- It obtains the internal tenant principal from the existing worker identity service and uses trusted server composition for tenant repositories.
- It accepts only `math.calculate@1.0.0`, with local-computation risk, no side effects, no approval requirement, and a plan-declared scope matching the capability definition.
- It rejects unsupported plans before claiming a step.
- It checks cancellation and stop gates before claim, after claim, and after the durable audit reservation immediately before dispatch; it checks again before result commit.
- It reserves append-only audit before handler invocation, uses the existing fenced lease, and stores only bounded validated JSON results.
- If a stop arrives after claim/dispatch and the existing repository cannot safely mark the step cancelled, the runner deliberately leaves the lease for expiry and explicit `recovery_required` handling. It does not replay uncertain work.

**CI evidence:** GitHub Actions run [44142092882](https://github.com/quickchefbooking-ship-it/Project-atlas-/actions/runs/44142092882) completed successfully on commit `28584bbb10080db0796e1b4e1ee66b54a2b465ed`: **1,161 tests passed, 1 warning**.

The implementation remains non-runnable in production until a real isolated host and durable storage are verified. It does not provide container isolation, process supervision, a queue consumer loop, or production configuration.


### Lifecycle checkpoint

The runner now also requires a thread-safe lifecycle controller to be in `READY` state. The lifecycle transitions are `STOPPED → STARTING → READY → DRAINING → STOPPED`, with a fail-closed `FAILED` state. Readiness cannot be declared unless all three deployment gates are true. Dispatch admission and draining share the lifecycle lock: once draining wins, no new dispatch can be admitted; already admitted work is counted, and `stop()` refuses to complete until every dispatch releases its slot. The controller does not wait for in-flight work or supervise an operating-system process; a real host supervisor must perform that wait/termination and cleanup.

**Latest exact-head CI:** [GitHub Actions run 44143111746](https://github.com/quickchefbooking-ship-it/Project-atlas-/actions/runs/44143111746) passed on commit `7d9d0a6d086e1e46046e976feb1665e5506bf33f`: **1,164 tests passed, 1 warning**.

### Published deployment and source reconciliation — 17 November 2026

A second strictly read-only inspection of the ATLAS Replit app confirmed:

- The published deployment exists, reports a successful build, and serves `https://wwe.atlasonepro.com` as a public Autoscale deployment.
- Replit deployment metadata exposes no deployed commit or build revision. A revision-filtered deployment-log search returned no logs, so the source currently served at that URL cannot be matched to GitHub or the workspace.
- The Replit workspace is on `main` at `2f182eaa87ee4ecab41e26963b1ff5b9050387d8`, with a clean working tree, but has no GitHub remote or upstream. Its configured remotes are `gitsafe-backup` and `subrepl-shared`.
- GitHub `main` remains `32471ea720edb5f10ca51aafaf9d45113d4e736c`; it does not match the workspace HEAD. None of the 62 currently open draft PR heads matches the workspace HEAD.
- The published success status does not prove that the deployment contains the workspace HEAD, GitHub `main`, or any active PR head.

No Git fetch, local ref update, file change, build, publish, secret access or deployment change was performed.

**Launch gate:** Before treating GitHub work as present in the live app, the owner must explicitly reconcile the Replit workspace with the authoritative repository and branch, then establish a reliable deployed source-revision signal. Do not overwrite the existing workspace or alter remotes automatically.

### Read-only build-revision endpoint

The application now exposes `GET /build-info` for deployment-source verification. It returns only:

- `revision`: a normalized 40-character Git SHA, or `null` when no valid revision is supplied;
- `status`: `known` or `unknown`.

The value is read only from `ATLAS_BUILD_REVISION`. Missing or malformed values are reported as unknown and are never echoed. The endpoint does not expose branch names, environment dumps, paths, credentials, or other deployment settings.

For this endpoint to attest the running deployment, the deployment/build pipeline must inject the exact full SHA of the source tree used for that build. Manually entering a guessed or stale value is not proof. Until the Replit build process supplies and independently verifies that value, `/build-info` is expected to report `unknown` and the source-reconciliation gate remains open.

