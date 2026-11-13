# Professor route and data ownership inventory

**Status:** source-code inventory only, reviewed against `app.py` and `atlas_engine/storage.py` at the identity/tenant-boundary work branch. This document does not change runtime behaviour or assign tenant ownership.

## Current security boundary

- `require_api_key` is the common FastAPI dependency on private/data routes. It verifies possession of one shared `X-API-Key`; it does not establish a human identity, organisation membership, role or tenant.
- `API_REQUIRE_AUTH` can disable that gate for local development. A production deployment must not rely on that mode.
- `GET /health` is intentionally public and returns the task API health response.
- `GET /professor/sources` and `GET /professor/learning` serve static operator pages without the API-key dependency. Their data APIs are protected, but the pages themselves are public shells and must not embed credentials or private data.
- The current task request/recovery/cancellation models accept caller-supplied `actor` strings. These are untrusted audit labels, not verified identity.
- No tenant identifier or membership foreign key appears in the current core SQLite table definitions listed below.

## Route inventory

All routes below other than the public health endpoint and static HTML shells are currently protected by the shared API-key dependency. “Protected” here means shared-key possession only, not user-level authorisation.

| Route | Data/action | Tenant and identity implications |
|---|---|---|
| `GET /health` | Service/task health | Public; keep response aggregate and free of personal/task data. |
| `GET /professor/sources` | Static source operator UI | Public shell; ensure no embedded secrets or private data. |
| `GET /professor/learning` | Static learning operator UI | Public shell; ensure no embedded secrets or private data. |
| `GET /sources` | Source registry metadata | Shared-key protected; registry is currently global. |
| `GET /sources/documents` | Source-document review metadata | Shared-key protected; source records and reviewer metadata need owner scope. |
| `POST /sources/import` | Stage manually supplied source batch | Shared-key protected; source ownership and reviewer attribution needed. |
| `POST /sources/fetch` | Fetch public provider material and stage it | Shared-key protected; global staging currently, future tenant-specific provenance needed. |
| `POST /sources/fetch-url` | Fetch allowlisted public page and stage it | Shared-key protected; global staging currently, future tenant-specific provenance needed. |
| `GET /sources/search` | Search approved source material | Shared-key protected; search must be tenant-filtered before private workspaces exist. |
| `GET /tasks` | List tasks | Shared-key protected; high-priority tenant isolation. |
| `POST /tasks` | Create task | Shared-key protected; creation must derive tenant from verified principal, never request input. |
| `GET /tasks/{task_id}` | Read task | Shared-key protected; object-level tenant check required. |
| `POST /tasks/{task_id}/run` | Execute task | Shared-key protected; tenant, capability scope and action policy required. |
| `GET /tasks/{task_id}/attempts` | Read attempt history | Shared-key protected; inherit task tenant and verify same-tenant reference. |
| `POST /tasks/{task_id}/cancel` | Request cancellation | Shared-key protected; actor label is unverified; require task-write/cancel scope and audit principal. |
| `GET /tasks/{task_id}/cancellation` | Read cancellation state | Shared-key protected; inherit task tenant. |
| `GET /tasks/{task_id}/retry-schedules` | Read retry schedules | Shared-key protected; inherit task tenant and avoid exposing internal scheduling metadata. |
| `GET /tasks/retries/due` | List due retries | Shared-key protected; operator/service scope; tenant-aware worker policy needed. |
| `POST /tasks/retries/expire` | Expire retry schedules | Shared-key protected; privileged maintenance scope and audited service identity needed. |
| `POST /tasks/recovery/scan` | Scan expired attempts | Shared-key protected; privileged maintenance scope and audited service identity needed. |
| `GET /tasks/recovery-required` | List recovery-required attempts | Shared-key protected; operator scope and tenant-filtered results needed. |
| `POST /tasks/{task_id}/recovery-decision` | Record retry/failure decision | Shared-key protected; actor label is unverified; high-risk operator action requiring approval and audit. |
| `GET /tasks/{task_id}/evaluations` | Read evaluations | Shared-key protected; inherit task tenant. |
| `GET /lessons` | List lessons | Shared-key protected; lessons may contain sensitive evidence; tenant and reviewer scope required. |
| `POST /proposals` | Create improvement proposal | Shared-key protected; tenant and verified creator identity required. |
| `GET /proposals` | List proposals | Shared-key protected; tenant-filtered reviewer/operator access required. |
| `POST /proposals/{proposal_id}/review` | Approve/reject proposal | Shared-key protected; caller-supplied approver label is not identity; require verified reviewer scope and action-specific approval. |
| `GET /learning/overview` | Learning/quality aggregates | Shared-key protected; aggregates must be tenant-scoped to prevent cross-customer inference. |
| `GET /dashboard` | Combined task/lesson/proposal dashboard | Shared-key protected; all component queries must use the same verified tenant context. |
| `GET /media/health` | Media subsystem health | Shared-key protected in current route declaration; keep output operational and non-sensitive. |
| `POST /media/generate-image` | Generate image from prompt | Shared-key protected; prompts may contain personal data; require tenant scope, quotas and content policy. |
| `POST /media/generate-video` | Generate video from prompt/narration | Shared-key protected; prompts/narration may contain personal data; require tenant scope, quotas and content policy. |

## Core SQLite tables

The current `init_db` schema defines these ten tables. None currently has a tenant ownership column or tenant membership foreign key.

| Table | Main relationship | Migration priority |
|---|---|---|
| `tasks` | Root task title, description, criteria, status and result | Critical: may contain user-provided personal or commercially sensitive content. |
| `task_attempts` | Child of task; worker, lease and attempt state | Critical: enforce same-tenant composite relationship to task. |
| `task_recovery_decisions` | Child references task and attempt; actor/reason | Critical: verified actor and tenant-scoped audit trail. |
| `task_cancellations` | Child references task and attempt; actor/reason | Critical: verified actor and same-tenant references. |
| `task_retry_schedules` | Child references task and originating/claimed attempts | Critical: isolate worker queues and internal retry metadata. |
| `evaluations` | Child of task; reasons and missing requirements | High: evaluation text may reveal task contents. |
| `lessons` | Child of task; summary and evidence JSON | Critical: evidence may contain personal data; validation/review identity needed. |
| `proposals` | Optional task reference; problem/evidence/change and reviewer labels | High: isolate proposal content and verify reviewer identity. |
| `sources` | Source registry | High: decide whether global platform catalog or tenant-owned registry; make scope explicit. |
| `source_documents` | Child of source; content, URI, trust and review state | Critical: content and reviewer attribution require explicit ownership and access rules. |

## Additional code paths to include in the full inventory

The API route list is not the whole data boundary. The migration review must also cover:

1. Direct storage functions called by `TaskManager`, `LearningMemory`, `ImprovementManager` and source adapters.
2. Static operator pages and their fetch calls, including where API keys are held in browser memory.
3. Startup imports of bundled knowledge and registration of global public-source adapters.
4. Background/worker execution, retries, lease recovery, cancellation and media generation.
5. Logs, generated media files, temporary files, backups and any future caches or search indexes.

## Recommended implementation order

1. Keep the existing single-owner prototype private while the identity and tenant model is incomplete.
2. Finish the route-to-storage call graph and identify every direct table read/write, including indirect task-child lookups.
3. Decide which source catalog records are platform-global and which imported documents are tenant-owned; do not assume all sources share the same ownership model.
4. Design a tenant-aware repository/storage interface so every tenant-owned read, list, search, aggregate, update and delete requires a verified server-side tenant context.
5. Rehearse a backup and additive migration against a copy. Explicitly map existing single-owner records to one owner tenant; quarantine uncertain records.
6. Add route-level and storage-level negative tests for cross-tenant read, list, search, count, update, cancellation, retry, review and export.
7. Only then wire a selected OIDC provider and authenticated principal into the API. Provider selection remains a separate decision gate.

## Explicit non-goals for this inventory

- No authentication provider selected or configured.
- No tenant columns, migrations or data backfills applied.
- No endpoint behaviour changed.
- No real user, housing, benefits or employment data collected.
- No deployment, merge or external side effect authorised.
- No claim of UK GDPR, SOC 2, ISO 27001 or Cyber Essentials compliance.
