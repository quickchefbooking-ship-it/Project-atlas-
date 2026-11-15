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
