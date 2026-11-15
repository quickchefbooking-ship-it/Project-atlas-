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
- `GET /professor/conversations/{conversation_id}/audit/verify` recomputes the current tenant/owner hash chain and reports broken record IDs without returning raw content. Verification covers the full chain for that owner, across conversations.
- `GET /professor/conversations/{conversation_id}/trace` provides one read-only view of the owned conversation messages, its audit records, chain verification and any conversation feedback the caller is authorized to read. Feedback is omitted with an availability flag when the caller lacks `evaluations:read`.
- SQLite triggers prevent updates and deletes. Hash chaining makes alteration detectable when the chain is independently verified; it is not a substitute for externally anchored tamper-evident storage, backups, or production-grade audit retention.
- The trace records what the application supplied to the provider, not proof that a model internally attended to or correctly used each item. No automatic learning or execution authority is created.


## Browser-first Professor chat workspace

- `GET /professor/chat` serves the mobile-first browser conversation interface.
- The page accepts a short-lived OIDC bearer access token issued by the deployment's identity provider. The token is held only in page memory and cleared when the user disconnects or reloads; it is not written to browser storage or sent in a URL.
- The page calls the authenticated conversation, list, read, delete and unified trace routes using the `Authorization: Bearer` header. It does not use the legacy API-key field or trust client-supplied tenant/scope values.
- The page can list and reopen saved conversations, start a new conversation, send turns, inspect the read-only trace and explicitly delete a conversation.
- This is a browser client, not an identity provider or login system. A deployment must provide a secure OIDC sign-in flow and issue appropriately scoped access tokens before general users can use it. Do not paste tokens into shared devices.
- A missing identity configuration, tenant database, required scope or reasoning provider is shown as an API error; the page does not fabricate model responses.


## Deployment-owned OIDC configuration

The repository already contains a cryptographic JWT verifier (`PyJWTTokenVerifier`) that uses a pinned deployment-configured JWKS URL. The server constructs it only when all five settings below are present. The browser does not validate JWTs and must never be treated as the authority for identity or permissions.

Required server environment:

- `ATLAS_OIDC_ISSUER`: exact HTTPS issuer value expected in the token's `iss` claim (no trailing slash, matching the identity provider metadata exactly).
- `ATLAS_OIDC_AUDIENCE`: API audience expected in the access token.
- `ATLAS_OIDC_JWKS_URI`: HTTPS JWKS endpoint for that issuer.
- `ATLAS_OIDC_ALLOWED_ALGORITHMS`: explicit comma-separated allowlist; supported values are `RS256`, `PS256` and `ES256`. Use only algorithms actually configured by the issuer.
- `ATLAS_MEMBERSHIP_DB_PATH`: dedicated writable path for the server-controlled tenant membership registry.

Also required for conversation use:

- `ATLAS_TENANT_DATA_DB_PATH`: dedicated tenant conversation/plan database. It must not resolve to the core task database or membership database.
- The deployment must separately configure the opt-in reasoning provider settings above. Without them, the chat API correctly returns 503.

### Provisioning sequence

1. Register an API/resource audience with the organisation's OIDC provider. Configure the access-token issuer, audience and JWKS URI exactly; issue access tokens for this API, not ID tokens.
2. Supply the five OIDC settings and two database paths through the hosting platform's secret/environment configuration. Do not put secrets or tokens in source control, URL parameters, build logs or client JavaScript.
3. Provision the tenant and issuer/subject membership through a trusted operator-controlled provisioning process using `SQLiteMembershipRegistry`. Grant only the required scopes: `conversations:read` and `conversations:write`; grant `conversations:delete` only where deletion is intended. Never derive scopes from provider role strings or browser input.
4. Configure a supported reasoning endpoint and model only after its privacy, retention, cost and data-processing terms have been approved. Keep the provider disabled until that decision is made.
5. Restart the service, then test `GET /identity/me` with a short-lived API access token. Confirm the issuer, subject, tenant and server-derived scopes. Next test list, create, reopen, trace and delete using a non-production tenant. Confirm that another tenant/owner cannot access those records.
6. Before public rollout, replace or formally approve the SQLite prototype storage, add managed backups, TLS, rate limits, retention/deletion policy, monitoring, incident handling and a security review.

The browser workspace now calls `GET /identity/me` before listing conversations and checks that the verified principal has `conversations:read` and `conversations:write`. This improves diagnostics; the server remains the security boundary. The page still uses a manually supplied short-lived token until a hosted OIDC authorization-code flow with PKCE and a registered redirect URI is implemented. Do not use manual token entry as the general-user sign-in experience.


## Hosted sign-in readiness (Stage 1)

The public `GET /identity/login-readiness` endpoint reports whether the
server-side OIDC verifier and hosted-login client settings are present. It
returns setting names that are missing, but never returns issuer URLs, client
IDs, secrets, tokens, tenant memberships or permissions. It is a deployment
diagnostic only; it does not authenticate users or start a login transaction.

The hosted-login client settings reserved for the next implementation step are:

- `ATLAS_OIDC_CLIENT_ID`: public OIDC client identifier registered for AtlasOnePro.
- `ATLAS_OIDC_REDIRECT_URI`: exact HTTPS callback URL registered with the provider.

The intended flow is Authorization Code with PKCE (S256), using a maintained
OIDC client library and server-side token exchange/session handling. The
browser must not receive a client secret or store access/refresh tokens in
browser storage. State, nonce and PKCE verifier must be transaction-bound,
single-use and protected against CSRF and replay. The callback must validate
the issuer, audience, nonce and token response before issuing an opaque,
HttpOnly, Secure, SameSite=Lax application session. Logout must revoke or
invalidate the server session and clear the cookie.

**Deployment dependency:** the actual provider issuer, registered client ID,
exact callback URI, token/API audience and provider-supported signing
algorithm must be supplied by the deployment owner. Until those values are
known and the callback implementation has passed provider-backed tests, the
manual short-lived bearer-token entry remains a restricted development bridge.
Do not expose it as general-user sign-in. The readiness endpoint and chat
indicator are diagnostic scaffolding, not a completed hosted login.


## Identity-provider recommendation

For the first commercial multi-tenant release, the provisional recommendation is
**Auth0 (OIDC) as the customer identity provider**, using its hosted Universal
Login and a confidential server-side web application. The reasons are its
standard OIDC integration model, hosted login, and explicit B2B organisation
capabilities. Auth0's published Free tier currently includes up to five
organisations; organisation-scoped RBAC and larger organisation needs may
require a paid tier. Recheck current plan limits and terms before launch.

This is a recommendation, not an account selection or provider activation.
The existing Atlas tenant-membership registry remains the authority for Atlas
tenant IDs and scopes; Auth0 organisation metadata or token role claims must
not grant Atlas permissions by themselves. The application must map a verified
Auth0 issuer/subject to a provisioned Atlas membership.

Implementation target:

- Auth0 tenant issuer and discovery metadata, pinned and checked against the
  configured issuer.
- One confidential web application registration; client secret held only in
  deployment secret storage.
- Authorization Code flow with PKCE (S256), state and nonce validation.
- Exact HTTPS callback and logout URLs; no wildcard redirects.
- Server-side opaque sessions; cookies Secure, HttpOnly and SameSite=Lax.
- Access and refresh tokens remain server-side; no tokens in browser storage,
  URLs, logs or rendered HTML.
- CSRF protection on state-changing cookie-authenticated routes, session
  rotation after login, bounded idle/absolute expiry, and explicit logout.
- API access tokens must have the Atlas API audience; ID tokens are never
  accepted as API bearer tokens.
- MFA and organisation connection policies are deployment decisions to be
  enabled before external customer onboarding.

Required deployment values for the Auth0 implementation will include the
exact issuer (for example, the tenant's Auth0 domain), API audience, JWKS
endpoint, registered client ID, client secret, exact callback URL, exact
post-logout URL, and a strong session-signing secret. No sample domain or
credential is treated as a real configuration.

The code remains provider-neutral at the API verification boundary. Auth0 can
be replaced or supplemented by another standards-compliant OIDC provider
without trusting provider role claims as Atlas permissions.
