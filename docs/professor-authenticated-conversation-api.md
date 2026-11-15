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
