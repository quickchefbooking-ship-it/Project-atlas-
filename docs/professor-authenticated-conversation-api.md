# Professor authenticated conversation API

This change connects the text-only reasoning service to the verified identity
and tenant conversation repository. It remains opt-in and fail-closed.

## Runtime configuration

The authenticated API uses the isolated tenant data database already configured
through `ATLAS_TENANT_DATA_DB_PATH`. Conversation tables are initialized in
that database alongside the tenant plan, step and evidence tables.

The reasoning provider remains disabled unless all of the following are
configured by the deployment owner:

- `ATLAS_LLM_PROVIDER=openai_compatible`
- `ATLAS_LLM_CHAT_COMPLETIONS_URL` — deployment-owned HTTPS endpoint (or loopback
  HTTP for local self-hosted inference)
- `ATLAS_LLM_MODEL`
- Optional `ATLAS_LLM_API_KEY`, supplied through the deployment secret store
- Optional bounded timeout/response settings documented in
  `professor-reasoning-provider-adapter.md`

No provider key or endpoint is committed. No hosted provider is selected by
default and no paid service is activated by this change.

## Identity and scopes

Every conversation route requires `require_verified_principal`. The caller
cannot submit a tenant ID, owner ID, role, scope, or message role. Server-side
membership must grant the relevant scopes:

- `conversations:read` for listing and reading
- `conversations:write` for creating and continuing conversations
- `conversations:delete` for deletion

A deployment must provision these scopes in its trusted membership registry.
The API does not infer them from client claims.

## Routes

- `POST /professor/conversation` — accepts only a user message and optional
  existing conversation ID. Creates a conversation when no ID is supplied.
- `GET /professor/conversations` — lists the caller's conversations.
- `GET /professor/conversations/{conversation_id}` — reads bounded message
  history owned by the caller.
- `DELETE /professor/conversations/{conversation_id}` — removes the content
  and records the repository's minimal deletion tombstone.

Assistant messages are persisted only after the injected provider returns a
valid typed response. The provider adapter has no tools or function calling.
The conversation API does not invoke the capability runtime or task executor.

## Operational boundaries

- The endpoint remains unavailable when verified identity, tenant storage, or
  the explicitly configured reasoning provider is missing.
- Provider failure returns a generic 503. The user turn is not persisted unless
  the provider returns a valid response, avoiding incomplete conversation
  records when reasoning fails.
- No production database migration, OIDC tenant provisioning, provider secret,
  deployment, voice connection, or external action is performed here.
- This implementation uses the existing SQLite tenant-data prototype. A
  production deployment still needs a reviewed migration and durable,
  backed-up database configuration before enabling the routes.
- Apply rate limits, retention policy, operational monitoring and abuse
  controls at the deployment boundary before public exposure.


## Model-assisted plan proposals

`POST /professor/tenant/plans/suggest` accepts an objective from a verified
tenant member and asks the configured text provider for a structured proposal.
The proposal is parsed against a strict JSON contract and the application-owned
capability registry. Capability risk, version, required scopes, timeout and
resource budget are derived by trusted application code; the model cannot set
or escalate them.

A valid proposal is persisted only as a tenant-owned `DRAFT`. The route does
not prepare, approve, dispatch or execute the plan. The existing separate
prepare workflow performs deterministic capability and scope checks, and
external/privileged work remains blocked pending a future action-bound
approval implementation. Model-produced text is never treated as proof of
approval or capability authority.


## Evidence-aware planning context

Plan suggestions now retrieve a maximum of three short excerpts from approved
shared reference material. The context builder admits only the explicitly
listed public/curated source classes registered as read-only. Approval-gated
manual imports and other source classes are excluded even if they are present
in the general source index. Pending and rejected documents remain excluded by
the underlying retrieval layer.

Each returned evidence item carries its document ID, title, URL, trust label
and content hash so a reviewer can trace the reference. Excerpts are capped and
are explicitly labelled as untrusted data in the model context; embedded
instructions are not to be followed. This is lexical retrieval over a bounded
local index, not semantic search, a truth score, or a guarantee of completeness.
The model's proposal still passes the same trusted capability validation and
is saved only as a DRAFT. No evidence item grants permission to act.


## Conversational reasoning context

The authenticated conversation route prepends a fixed Professor policy message
to the provider request and retrieves up to three short excerpts from the same
approved, shared, read-only reference classes described above. The returned
response includes the evidence identifiers and provenance fields used for that
turn. Conversation history persists only user and assistant messages; the
system policy and retrieved excerpts are reconstructed for each request rather
than stored as user-authored chat content.

## Non-mutating plan preview

- `GET /professor/tenant/plans/{plan_id}/preview` checks a tenant-owned DRAFT
  against the trusted capability registry and the verified caller's scopes.
- The response reports ordered steps, readiness, blocked steps and reasons.
- Preview does not change plan state, prepare work, approve actions or execute
  capabilities. Preparation remains a separate explicit request.


## Evaluation and lessons foundation

Professor now has tenant/owner-isolated append-only evaluation records:

- `POST /professor/tenant/evaluations` records explicit feedback or an observed
  outcome for an owned conversation, plan or task.
- `GET /professor/tenant/evaluations` lists only records belonging to the
  verified tenant and owner, with bounded filtering and pagination.
- Ratings, notes and evidence provenance are validated and size-bounded.
- Update and delete are blocked at the SQLite schema layer to preserve history.

These records are a reviewable evidence trail, not an autonomous learning
mechanism. They do not rewrite prompts, policies, capability permissions,
provider settings or model weights. Any future lesson promotion must be a
separate human-reviewed workflow with provenance and a reversible change log.


## Aggregate feedback review

- `GET /professor/tenant/evaluations/summary` returns owner-scoped counts by
  outcome, number of rated records and average rating.
- The summary deliberately excludes free-text notes and evidence payloads.
- It is descriptive feedback, not a correctness score or an autonomous learning
  signal. Human review remains required before any lesson is proposed or adopted.


## Tenant lesson proposal and independent review

- `POST /professor/tenant/lessons` creates a human-authored lesson candidate
  linked to 1–20 evaluation IDs owned by the proposer.
- `GET /professor/tenant/lessons` lists candidates and their latest review
  status within the verified tenant.
- `POST /professor/tenant/lessons/{candidate_id}/decision` records an
  approval or rejection. The reviewer needs `lessons:approve` and must be a
  different verified identity from the proposer.
- Candidate content and decision history are immutable/append-only. A second
  decision cannot silently overwrite the first.
- Approval means only that a tenant reviewer accepted the text as a
  tenant-local reference. It does not insert it into execution memory, the
  system prompt, global learning, model training, capability permissions or
  automation. Runtime promotion remains disabled pending a separately reviewed
  attribution and retrieval design.
- The proposer supplies the lesson text; the model does not autonomously
  manufacture or approve lessons. Evaluation references are checked against
  the proposer's own records.


## Reasoning audit trail

- Each successfully persisted Professor turn receives an append-only audit record.
- The record stores SHA-256 hashes of the user message, assistant response and effective system/evidence context; provider/model identifiers; bounded evidence provenance; and a per-owner hash-chain link.
- Raw prompts, answers, credentials and retrieved excerpts are not duplicated in the audit table.
- `GET /professor/conversations/{conversation_id}/audit` returns records only after verifying ownership of the conversation. The route is read-only and uses the verified identity boundary.
- SQLite triggers prevent updates and deletes. Hash chaining makes alteration detectable when the chain is independently verified; it is not a substitute for externally anchored tamper-evident storage, backups, or production-grade audit retention.
- The trace records what the application supplied to the provider, not proof that a model internally attended to or correctly used each item. No automatic learning or execution authority is created.
