# AtlasOnePro capability registry — prototype boundary

**Status: immutable registry plus bounded runtime validation and a small tenant-scoped execution vertical slice. This is not a general plugin system.**

The initial `atlas_engine.capability_registry` module defines a read-only catalogue built from application-owned definitions at startup. It deliberately has no runtime registration or update method. Task payloads, retrieved documents and external providers cannot add or alter definitions.

Each definition records:

- stable name and version;
- object-shaped input and output schema metadata;
- declared scopes;
- risk class (`read_only`, `local_write`, `external_write` or `privileged`);
- whether side effects exist;
- a bounded execution timeout;
- whether action-specific approval is required;
- optional idempotency-key scope and a validated retry contract.

Safety constraints:

- external-write and privileged capabilities require approval in their definition;
- read-only capabilities cannot declare side effects;
- schema metadata is copied into immutable structures;
- remote/recursive schema references and non-JSON values are rejected;
- retry contracts must match the registered capability name/version, prove idempotency and duplicate suppression, declare side effects, include a test-evidence reference, and bind an idempotency-key scope;
- schemas are checked against Draft 2020-12 at registration and input/output objects are validated at runtime with finite-JSON and 64-KiB bounds;
- the registry itself does not authenticate users or grant scopes. The separate tenant execution route requires a verified principal, plan execution scope, capability scopes, a prepared plan and a fixed application-owned handler binding;
- the current built-in handlers are restricted to local arithmetic and read-only Crossref/evidence/report processing. No external-write or privileged handler is registered.

## Current execution boundary

A tenant-scoped `POST /professor/tenant/plans/{plan_id}/execute-next` route is wired. It executes one dependency-ready step per request only after a plan has passed readiness preview and the caller has verified identity, `plans:execute`, and all registered capability scopes. It uses fixed application-owned handlers; it does not load plugins or call task-supplied code.

The current catalogue contains bounded local arithmetic and read-only Crossref research, evidence bundling, deterministic evaluation and report generation. Crossref is the only built-in handler that performs network I/O; it currently runs in-process with a bounded HTTP adapter, not an isolated worker. No external-write or privileged handler is registered. There is no unattended scheduler.

Remaining controls before expanding this vertical slice: add a global execution kill switch, independently verify evidence references, strengthen execution audit reservation and resource isolation, and isolate network-capable handlers before adding further network or credential access. The current implementation must not be presented as a general-purpose or production-ready plugin executor.

This is a prototype foundation, not evidence of SOC 2, ISO 27001, Cyber Essentials or UK GDPR compliance.
