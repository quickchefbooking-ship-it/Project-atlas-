# Tenant-scoped data access: implementation plan

## Status

Design and inventory only. This document does not add tenant columns, alter the application database, change routes, or enable tenant access. The current core schema remains single-tenant/global and must not be represented as company-isolated.

## Verified repository findings

The current core SQLite schema is created by `atlas_engine/storage.py`. Its principal record families are:

- `tasks`: top-level work records.
- `task_attempts`, `task_recovery_decisions`, `task_cancellations`, `task_retry_schedules`: task-owned execution and recovery records.
- `evaluations`, `lessons`, `lesson_usage_events`: task/lesson learning records.
- `proposals`: optional task-linked improvement proposals.
- `sources`, `source_documents`: shared source catalogue and source content.
- `lesson_experiment_runs`: offline experiment evidence; it currently has no tenant owner.

The existing foreign keys mostly express record relationships, not tenant ownership. The current `get_connection()` opens the configured core database and enables SQLite foreign-key enforcement, but it does not establish a tenant context. The membership registry is deliberately stored separately and does not retrofit the core schema.

## Required target model

1. A tenant-owned root record must carry a non-null `tenant_id` with a foreign key to the tenant registry (or a future consolidated tenant table).
2. Every tenant-owned child must be linked to its parent with tenant-consistent composite constraints, not merely a globally unique child ID.
3. Every user-facing read, write, update, delete, export and background-job query must receive a trusted immutable `RequestPrincipal` created by the future verified authentication boundary.
4. Tenant identity comes only from that principal. Never accept a request-body, query-string, path, header, or client-supplied actor field as proof of tenant membership.
5. Queries must include tenant predicates at the database boundary. Application-level post-filtering is not an acceptable isolation control.
6. Resource lookup should combine resource ID and principal tenant in one query. A missing or cross-tenant resource should return the same externally visible not-found/denied response.
7. Child operations must prove ownership through the parent chain in the same transaction. A child ID alone is never sufficient.
8. Background workers require an explicit, narrowly scoped service principal or a durable tenant-bound job envelope. They must not run as an implicit global administrator.
9. Global/shared data (for example public source catalogue records) must be explicitly classified and separated from customer-private data. A shared record must never become a back door to tenant-private content.
10. Administrative cross-tenant access requires a separate explicit permission, strong audit event, and purpose/reason; no implicit support override.

## Proposed ownership map for migration design

| Record family | Proposed ownership | Required treatment |
| --- | --- | --- |
| tasks | tenant-owned root | Add tenant ownership and tenant-scoped CRUD |
| attempts | inherits task tenant | Enforce same-tenant task/attempt relationship |
| recovery decisions | inherits task tenant | Enforce same-tenant task and attempt relationship |
| cancellations | inherits task tenant | Enforce same-tenant task and attempt relationship |
| retry schedules | inherits task tenant | Enforce same-tenant task and attempt relationship |
| evaluations | inherits task tenant | Enforce same-tenant task relationship |
| lessons | inherits task tenant | Enforce same-tenant task relationship |
| lesson usage events | inherits task tenant | Ensure task, attempt and lesson all resolve to same tenant |
| proposals | tenant-owned; task may be optional | Require tenant even when task_id is null; validate linked task tenant |
| sources/source_documents | classification required | Decide shared catalogue vs tenant-private source/content before migration |
| lesson experiment runs | classification required | Decide global offline test evidence vs tenant-specific evidence; do not expose customer payloads |

This is a proposed ownership model, not a claim that these records are currently tenant isolated.

## Repository/API boundary

A future tenant repository should accept a `RequestPrincipal` as a required constructor or method argument and centralise:
- principal type and active-membership validation;
- required-scope checks;
- tenant predicate binding on every SQL statement;
- tenant-consistent parent/child joins;
- transaction boundaries for multi-record operations;
- generic not-found behavior for cross-tenant identifiers.

Avoid a generic raw-SQL escape hatch in request handlers. Keep low-level unscoped storage functions private to migration/admin tooling and isolated test fixtures. Do not retrofit public endpoints until a trusted token verifier and server-side principal dependency exist.

## Migration sequence and release gates

1. Freeze and inventory every table, index, foreign key, query, worker and route that touches customer data.
2. Decide the ownership classification for shared sources and experiment runs.
3. Write a versioned migration rehearsal against a disposable copy, including orphan detection and row-count/hash reconciliation.
4. Add tenant columns and composite tenant-consistency constraints in a new schema version; never silently infer ownership for ambiguous rows.
5. Backfill only from an independently verified ownership map. Quarantine unknown or conflicting rows; do not assign them to a default tenant.
6. Add tenant-aware repository methods and cross-tenant negative tests for every CRUD path and child relationship.
7. Add verified auth middleware and fail-closed route dependencies; keep routes unavailable until this is complete.
8. Run full migration rehearsal, rollback rehearsal, backup/restore test, concurrency tests and security review before any production rollout.

## Minimum acceptance tests

- Tenant A cannot list, fetch, update, delete or export Tenant B records.
- Tenant A cannot access Tenant B records by guessing task, attempt, lesson, proposal or document IDs.
- Child IDs cannot be paired with a parent ID from another tenant.
- A task, its attempts, evaluations, lessons, retry schedules and usage events cannot be mixed across tenants.
- Missing, inactive, revoked, ambiguous or malformed principals fail closed.
- A request cannot change tenant by supplying a different tenant ID in its payload or headers.
- Background jobs cannot cross tenant boundaries and cannot execute without an explicit service identity.
- Shared-source access follows a documented classification and cannot expose private source documents.
- Migration rejects ambiguous ownership and preserves verified row counts and relationships.
- No public route becomes tenant-enabled before verified authentication and all relevant tests pass.

## Current release blockers

- No OIDC provider has been selected or configured.
- No cryptographic token verifier or verified-principal HTTP dependency exists.
- Core business tables do not yet carry tenant ownership.
- Existing API-key authentication is not individual human identity.
- The membership registry is separate and not yet wired to core data access.
- Proposal review remains deliberately disabled (HTTP 503).
- The current SQLite design is not a multi-tenant production deployment.

## Safety boundary

This plan is not a production migration, certification, or deployment approval. Keep PR #10 draft and unmerged. Do not modify production data, enable tenant-facing routes, or claim SOC 2/ISO/Cyber Essentials certification from this work.


## Prototype implementation progress

The following isolated prototype files now exist on the draft identity/tenant branch:

- `atlas_engine/tenant_repository_prototype.py`: tenant-filtered task and attempt create/read/list/update/delete operations, with composite tenant/parent foreign keys.
- `tests/test_tenant_repository_prototype.py`: cross-tenant task and attempt access, generic not-found behavior, scope enforcement, update/delete boundaries and database-level child relationship tests.
- `atlas_engine/tenant_learning_repository.py`: isolated tenant-owned evaluation, lesson and proposal records with tenant-consistent composite foreign keys and tenant-filtered read/write methods.
- `tests/test_tenant_learning_repository.py`: cross-tenant read/write denial, scope enforcement, composite foreign-key rejection and cascade behavior.

These prototypes use caller-owned disposable SQLite connections and are not imported by the live application. They do not alter `atlas_engine/storage.py`, `DB_PATH`, existing global tables, HTTP routes, or production data.

The learning prototype deliberately requires a task parent for proposals. The live proposal schema permits a nullable task link; that ownership case remains part of the later full ownership design and must not be silently assigned a tenant during migration.

## Next implementation gates

1. Confirm CI for the new prototype modules and tests.
2. Extend the same tenant-consistent pattern to recovery decisions, cancellations, retry schedules and lesson-usage events.
3. Decide shared versus tenant-private ownership for sources, source documents and offline experiment evidence.
4. Complete a disposable migration rehearsal and ownership reconciliation design.
5. Only after those gates, design a verified-principal application integration. Do not wire the prototype into production storage before that review.

## Additional prototype progress: execution lifecycle

The isolated execution prototype now covers:

- recovery decisions, linked to the exact tenant/task/attempt tuple;
- cancellation records, linked to the exact tenant/task/attempt tuple;
- retry schedules, with both originating and claimed attempts constrained to the same tenant and task;
- lesson-use events, constrained so the task, attempt and lesson all belong to the same tenant/task chain.

`atlas_engine/tenant_execution_repository.py` and `tests/test_tenant_execution_repository.py` are prototype-only. The task-attempt prototype now exposes composite unique keys needed by these child constraints. All repository operations still require an immutable `RequestPrincipal`, apply tenant predicates, and use a caller-owned disposable SQLite connection. No live storage, route, worker, or production migration is changed.

## Ownership classification decision for design and rehearsal

Use the following conservative default for the migration design:

- **Sources:** a curated, explicitly approved public catalogue may be shared. Tenant-created or tenant-configured source records must be tenant-owned. Shared catalogue metadata must not imply shared access to fetched content.
- **Source documents:** tenant-private by default. A document may be promoted into a shared catalogue only through an explicit review/publication workflow that verifies rights, removes customer-confidential material, records provenance and creates an immutable approved shared copy. Never expose a private document merely because its source connector is shared.
- **Lesson experiment runs:** tenant-owned by default because their payload may contain task/lesson content. Cross-tenant aggregate metrics, if later needed, must be separately generated from minimised, de-identified data under an explicit policy; raw experiment payloads are not global.

These are target design rules for the rehearsal, not a claim that existing records have already been classified or migrated. Existing source/document/experiment rows require provenance and ownership review; ambiguous rows must be quarantined, not assigned to a default tenant.

## Updated Point 1 acceptance gate

Point 1 is considered prototype-complete only when all of the following are true:

1. Task, attempt, evaluation, lesson, proposal, recovery, cancellation, retry and lesson-use prototype repositories have tenant predicates and appropriate scope checks.
2. Composite foreign keys prevent cross-tenant parent/child combinations at the database layer.
3. Negative tests cover both repository access and direct SQL relationship violations.
4. The full CI suite passes on the latest branch head.
5. Source/document/experiment ownership rules are documented for migration rehearsal.

This does not complete the production data-layer migration. A schema-versioned migration, verified ownership mapping, orphan report, row-count/hash reconciliation, rollback rehearsal and backup/restore validation remain release gates.
