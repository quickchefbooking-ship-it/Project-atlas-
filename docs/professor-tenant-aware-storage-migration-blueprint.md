# Professor tenant-aware storage migration blueprint

**Status:** design only. This document is based on the current `atlas_engine/storage.py` implementation. It does not alter runtime code, create a migration, or backfill a database.

## Why a storage-level boundary is required

The current FastAPI shared API-key dependency is not a tenant boundary. A route-level check alone is insufficient if a helper can still fetch or mutate a record by a bare ID. Tenant context must be required at the repository/storage boundary for every tenant-owned operation.

The current SQLite connection helper enables foreign keys on each connection, which is a useful foundation. New tenant relationships should use database constraints as well as application checks.

## Current storage function inventory

The following functions currently read or write the named records. The list is intended to guide implementation and test coverage; it is not proof that every indirect call path has been audited.

| Storage function(s) | Current records | Required future tenant treatment |
|---|---|---|
| `save_task`, `get_task`, `list_tasks`, `update_task`, `claim_task` | tasks | Create with server-derived tenant; require tenant for get/list/update/claim. |
| `claim_task_with_lease`, `heartbeat_task_attempt` | tasks, task_attempts, cancellations, retry schedules | Worker lease must carry persisted tenant context; validate same tenant for every child row. |
| `mark_expired_task_attempts`, `list_recovery_required_attempts` | task_attempts, tasks, cancellations | System worker must scan by tenant or use an explicitly privileged global service identity; operator listing must be tenant-filtered. |
| `get_task_attempts` | task_attempts | Require tenant and prove parent task belongs to it. |
| `resolve_task_recovery`, `list_task_recovery_decisions` | recovery decisions, tasks, attempts | Require tenant plus verified operator principal; persist immutable actor subject and decision audit metadata. |
| `save_evaluation`, `complete_task_with_evaluation`, `get_evaluations_for_task` | evaluations, tasks, attempts | Enforce same-tenant parent references and tenant-scoped reads/atomic writes. |
| `persist_task_retry_schedule`, `expire_task_retry_schedules`, `list_due_task_retry_schedules`, `list_task_retry_schedules` | retry schedules, tasks, attempts, evaluations | Tenant-scoped scheduling and worker claims; no global cross-customer due-list by default. |
| `request_task_cancellation`, `get_task_cancellation`, `acknowledge_task_cancellation` | cancellations, tasks, attempts, evaluations | Require tenant and task/cancel scope; actor identity must come from verified principal. |
| `save_lesson`, `list_lessons`, `search_validated_lessons` | lessons, tasks | Tenant-scoped retrieval and review; validated lessons must never cross tenant boundaries unless explicitly published as a curated platform lesson. |
| `save_proposal`, `get_proposal`, `list_proposals`, `update_proposal_status` | proposals, tasks | Tenant-scoped proposal operations and verified reviewer identity. |
| `save_source`, `get_source`, `list_sources` | sources | Explicitly distinguish platform-global catalog from tenant-owned source configuration. |
| `save_source_document`, `get_source_document`, `get_source_document_by_hash`, `list_source_documents`, `review_source_document` | source_documents, sources | Define document ownership and deduplication scope; never expose private imported content across tenants. |
| `get_learning_overview` | tasks, evaluations, lessons | Every count, rate and recent-record query must be tenant-filtered to prevent aggregate leakage. |
| `get_database_status` | SQLite metadata | Operational-only endpoint; do not expose filesystem paths or schema details to ordinary tenant users. |

## Proposed ownership model

Introduce three identity/organisation concepts before assigning tenant IDs to existing records:

1. **Principal** — a verified identity subject from an OIDC issuer. The stable key is the issuer plus subject, not an email address.
2. **Tenant** — an organisation or personal workspace that owns records.
3. **Membership** — a server-side relationship between a principal and tenant, with active/revoked state and role assignments.

A principal may belong to more than one tenant. The selected tenant is a requested context only; the server must resolve active membership before creating an immutable request principal. Never accept a tenant ID or role in the request body as authority.

## Proposed schema shape (illustrative, not executable SQL)

- `tenants(id, name, status, created_at)`
- `principals(issuer, subject, status, created_at)`, unique on `(issuer, subject)`
- `tenant_memberships(id, tenant_id, issuer, subject, status, created_at, revoked_at)`, foreign-keyed to tenant and principal
- `tenant_membership_roles(membership_id, role, created_at)`
- `tenant_audit_events(id, tenant_id, actor_issuer, actor_subject, action, resource_type, resource_id, request_id, approval_id, occurred_at, metadata_json)`

Every tenant-owned table gains a non-null `tenant_id`. Child references should enforce same-tenant relationships, ideally by adding unique keys on `(tenant_id, id)` to parent tables and composite foreign keys such as `(tenant_id, task_id)` on child tables. Existing single-column foreign keys should be retained or replaced only in a tested rebuild migration.

## Table-by-table ownership decisions

| Existing table | Proposed ownership | Key constraint / note |
|---|---|---|
| tasks | Tenant-owned | Unique `(tenant_id, id)`; all lookups require tenant. |
| task_attempts | Inherit task tenant | Composite FK `(tenant_id, task_id)`; keep attempt ID globally unique or unique per tenant consistently. |
| task_recovery_decisions | Inherit task tenant | Composite references to task and attempt; verified actor subject, not free-text actor alone. |
| task_cancellations | Inherit task tenant | Composite references to task and attempt; cancel action scope. |
| task_retry_schedules | Inherit task tenant | Composite references to task and attempts; service worker must be scoped and audited. |
| evaluations | Inherit task tenant | Composite FK to task; aggregates filtered by tenant. |
| lessons | Inherit task tenant | Private by default; platform-shared lessons require a separate reviewed publication model. |
| proposals | Tenant-owned; optional task must share tenant | Reviewer identity is a principal reference, not a label. |
| sources | Explicitly classify platform-global or tenant-owned | Do not add a tenant ID until each source type's lifecycle is decided. |
| source_documents | Follow source visibility/owner | Deduplication key must include visibility/tenant boundary; a shared content hash must not disclose private document existence. |

## Migration safety gates

1. **Freeze scope:** confirm this is a single-owner development database and identify the owner tenant. Do not assume production or uploaded user data is disposable.
2. **Backup and restore rehearsal:** make a consistent backup, verify it can be restored, and record row counts and foreign-key checks before migration.
3. **Add identity tables:** create tenant/principal/membership structures additively. No OIDC provider should be activated until token verification and recovery are implemented.
4. **Backfill on a copy:** assign legacy records to one explicitly approved owner tenant. If ownership is uncertain, quarantine rather than guess.
5. **Rebuild child tables carefully:** SQLite often requires table rebuilds to add composite foreign keys. Use a transaction where supported, preserve indexes/triggers, run `PRAGMA foreign_key_check`, and compare row counts and key relationships.
6. **Dual verification:** before switching reads, compare tenant-scoped repository results with the known single-owner baseline. Ensure no record becomes invisible or duplicated.
7. **Negative tests:** test cross-tenant reads, lists, counts, searches, exports, updates, deletes, retries, cancellation, recovery, proposal review and source-document deduplication.
8. **Route cutover:** wire verified principal and tenant context into every route and storage call. Remove client-supplied actor/tenant authority.
9. **Rollback plan:** keep a tested backup and a documented rollback route. Do not perform destructive schema cleanup in the same release as the first tenant cutover.

## Non-goals and stop conditions

- This is not an authentication implementation and does not choose an identity vendor.
- No migration or data backfill is authorised by this design.
- No route is considered multi-tenant safe until both route and storage tests prove isolation.
- No user housing, benefit, health or employment records should be entered into this prototype.
- Do not enable autonomous execution, external actions or cross-tenant lesson sharing as part of the migration.
- Stop if existing data ownership, backup integrity, foreign-key integrity or rollback cannot be demonstrated.
