# AtlasOnePro capability registry — prototype boundary

**Status: registry metadata and unit tests only. No capability is executed or exposed through an API by this change.**

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
- the registry is descriptive only. It does not validate runtime payloads against JSON Schema, authenticate users, grant scopes, verify evidence independently, or execute handlers.

## Not yet enabled

There are no registered production capabilities, no external credentials, no plugin loading, no scheduler dispatch, and no external writes. The existing local arithmetic executor remains the only execution path and remains single-attempt.

Before wiring this registry into orchestration, add an actual schema validator with a pinned supported JSON Schema dialect, independently verify evidence references, bind capability handlers in application code, enforce identity/tenant/scope checks at the execution boundary, and test that unknown or mismatched capabilities are rejected. Keep all external-write handlers disabled until approval and identity controls are independently reviewed.

This is a prototype foundation, not evidence of SOC 2, ISO 27001, Cyber Essentials or UK GDPR compliance.
