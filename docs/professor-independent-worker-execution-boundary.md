# Professor independent worker — execution boundary

**Status: design and identity foundation in progress.** This document and the accompanying identity contract do not start a worker, enable task execution or change deployment configuration.

## Verified existing foundations

The current AtlasOnePro branch already contains reusable components:

- typed tenant-owned plans and explicit plan lifecycle states;
- a trusted, application-owned capability registry and bounded capability runtime;
- tenant-scoped step leases with worker IDs, attempt numbers, fencing tokens, expiry and heartbeats;
- append-only step events and bounded result records;
- dependency-aware step claiming;
- cancellation and recovery states in the existing task prototype;
- a staged autonomy policy that denies unknown actions and keeps high-impact actions human-controlled.

The key gap is composition: there is no independently running Professor worker process that obtains its own trusted identity, claims eligible work, invokes the capability runtime, verifies outcomes and reports completion. The existing HTTP `execute-next` route derives its worker ID from the human caller and is not a persistent worker.

## First implementation slice

### 1. Worker identity

The new `professor_worker_identity` contract creates an internal principal only from trusted server-side configuration. It uses a reserved internal issuer, a server-assigned worker ID, explicit tenant grants and a narrow allowlist of orchestration scopes plus `compute:local`.

- Disabled by default.
- No wildcard tenant grant.
- No identity or scope accepted from a browser request.
- No human-session impersonation.
- Unknown or privileged scopes rejected.
- The service returns the existing immutable `RequestPrincipal` type so existing tenant repositories can enforce tenant and scope checks without a second authorization implementation.

This is an in-process trust seam, not yet a distributed workload-identity system. Before running across hosts or containers, use the hosting platform's workload identity or mutually authenticated service credentials and bind those credentials to the same server-side tenant grant registry.

### 2. Worker lifecycle

Implement a separately supervised process with these states:

`disabled → starting → ready → draining → stopped`

The process must:
- obtain configuration from deployment-owned settings, never from task payloads;
- verify worker identity and tenant grants at startup;
- refuse to start if the global execution kill switch, worker enablement, database, audit store, capability runtime or isolation boundary is missing;
- claim only READY/RUNNING work that has passed plan validation and any required human approval;
- claim one step at a time using the existing tenant lease repository;
- heartbeat while work is active and stop on lost lease, cancellation, shutdown or deadline;
- re-check capability scopes and autonomy policy immediately before handler invocation;
- call only registered fixed handlers, never task-supplied code, shell commands or dynamic plugins;
- persist a bounded result or sanitized failure with the same lease/fencing token;
- verify acceptance criteria and write an evidence-backed report before marking the plan complete.

### 3. Execution isolation

The first worker must run only the deterministic local-computation capability in a disposable workspace. A temporary directory alone is not a security sandbox. Before any untrusted build/test command is run, provide OS/container isolation with:
- non-root user and read-only base filesystem;
- a dedicated writable workspace with path traversal and symlink protections;
- no host mounts, Docker socket, cloud metadata access or production credentials;
- network disabled by default;
- CPU, memory, process-count, disk and wall-clock limits;
- process-group termination and cleanup;
- immutable image/dependency versions and recorded build provenance.

The first slice must not run arbitrary repository scripts or shell commands. It can invoke only the fixed registered local capability and fixed test harness approved by application code.

### 4. Queue, recovery and idempotency

Reuse the existing tenant step lease and event repositories rather than adding a parallel queue. Add a scheduler/worker loop only after the worker identity is trusted. Preserve fencing tokens and idempotency keys across every attempt. Lease expiry must remain `recovery_required`; never automatically replay uncertain work. Cancellation must be checked before claim, before handler invocation, at safe checkpoints and before completion. A stale worker must never be able to commit an outcome.

### 5. Autonomy policy integration

The staged autonomy policy must be enforced by the worker runtime, not merely documented. Each operation must map to a typed action. The worker must pass all of:
1. worker identity and exact tenant grant;
2. plan state and dependency readiness;
3. capability registry identity/version/schema;
4. per-step scope authorization;
5. autonomy mode/action decision;
6. resource and time budgets;
7. audit reservation before execution;
8. live lease/fencing and cancellation checks.

Any missing or unknown check fails closed. The worker cannot edit its own policy, grants, identity, capability registry or autonomy level.

### 6. Reporting and learning

Every run report records task/plan/step IDs, worker ID, capability/version, start/end time, result state, test evidence, bounded error code, resource usage and any approval needed. Do not store secrets or raw sensitive payloads in the audit record. Candidate lessons are not promoted automatically; only validated lessons can be reused.

## Acceptance gates

| Gate | Required evidence |
| --- | --- |
| Identity | Distinct worker issuer/subject, explicit tenant grant, disabled-by-default, cross-tenant denial |
| Dispatch | One-step claim, live lease, fencing and no duplicate concurrent execution |
| Policy | Every action checked at runtime; unknown actions/capabilities denied |
| Isolation | No host secrets, no production mounts, no network by default, hard resource limits |
| Cancellation | Worker stops safely; stale or cancelled attempt cannot commit |
| Recovery | Expired lease is held for explicit reconciliation, never blindly replayed |
| Audit | Durable reservation before invocation and append-only outcome event |
| Verification | Fixed test harness and acceptance criteria pass before success |
| Reporting | Evidence-backed status and bounded resource report |
| Owner control | Global stop works; worker cannot self-promote, merge or deploy |

## Current status and non-goals

This first change adds only the worker identity contract and its negative tests. It does not:
- start a background process or schedule;
- enable `ATLAS_CAPABILITY_EXECUTION_ENABLED`;
- grant any tenant or configure a worker in production;
- run shell commands or arbitrary code;
- introduce external model/API calls or paid infrastructure;
- merge, deploy, change secrets or touch production data.

Next implementation task: connect this identity contract to a one-step, sandbox-only worker runner, with runtime autonomy checks, kill-switch enforcement, cancellation and audit reservation.
