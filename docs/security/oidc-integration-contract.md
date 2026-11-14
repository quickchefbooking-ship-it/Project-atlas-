# OIDC integration contract for Professor

Status: provider-neutral engineering contract. No identity provider is selected or configured.

This document defines the boundary a future identity adapter must satisfy. It is not an authentication implementation and must not be used to construct principals from unverified token claims.

## Trust boundary

The HTTP application may create a `RequestPrincipal` only after all of the following succeed:

1. A configured provider is selected by deployment configuration, with an exact allowlisted issuer and expected audience/client ID.
2. The bearer token is parsed with strict size and format limits.
3. The token signature is verified using keys obtained from the configured issuer's trusted JWKS endpoint. Key selection, rotation, cache expiry and unavailable-key behavior are explicit. No algorithm is accepted merely because the token header requests it; algorithms are allowlisted by configuration.
4. Exact issuer and audience checks pass. If multiple audiences are present, the application validates the intended audience and applicable authorized-party claim.
5. Expiry and not-before claims are valid using a bounded clock-skew policy. Required subject and token claims are present and correctly typed.
6. The token is intended for this API, not merely a valid token for another client or service.
7. A server-controlled membership lookup resolves the issuer/subject pair to an active membership and tenant. Tenant ID is never accepted from request JSON, query parameters or an untrusted display claim.
8. Provider roles or groups are mapped through a server-controlled allowlist to narrow application scopes. Unknown roles grant nothing.
9. A server-only constructor creates the immutable `RequestPrincipal` for the current request. The principal is never deserialized from a client payload.

Any failure, timeout, unavailable JWKS, unavailable membership store, ambiguous tenant mapping or missing configuration must deny access. There is no fallback from human identity to the shared API key.

## Required adapter responsibilities

The future adapter should expose three separate responsibilities rather than one opaque "login" helper:

- **Token verifier:** verifies cryptographic and registered-claim requirements and returns a minimal verified identity record (issuer, subject, audience, issued/expiry timestamps and approved provider attributes).
- **Membership resolver:** maps the verified issuer/subject to an active tenant membership using server-controlled data; supports revocation and multiple-tenant membership without guessing a default tenant.
- **Scope mapper:** maps approved provider groups/roles and application policy to a bounded set of scopes. Client-supplied scopes are ignored.

Only the composition layer may create `RequestPrincipal`. Keep raw bearer tokens, ID tokens, refresh tokens and secrets out of logs, task payloads, experiment records and audit display fields.

## HTTP and session requirements

- Prefer a standard Authorization: Bearer header for API access; reject tokens in URLs and request bodies.
- Define login, callback, logout, refresh and session-revocation behavior for the selected provider before exposing browser sessions.
- Use secure, HttpOnly, SameSite cookies for browser sessions where applicable; enforce CSRF protection on cookie-authenticated state-changing requests.
- Validate redirect destinations against an exact allowlist. Use PKCE for authorization-code flows and state/nonce validation.
- Apply request size, rate and timeout limits to auth endpoints. Return generic authentication failures without leaking token-validation details.
- Keep API keys for service-to-service/local operations distinct from human-user identity. Never let an API key satisfy a human-review scope.

## Mandatory negative tests

The provider adapter is not ready until tests cover invalid signature, unknown signing key, disallowed algorithm, wrong issuer, wrong audience, wrong authorized party where applicable, expired token, future not-before, missing subject, malformed claims, JWKS outage, key rotation, membership not found, revoked membership, ambiguous tenant membership, unknown role, scope escalation attempts, forged tenant ID, token leakage prevention and session/CSRF failures.

Integration tests must additionally prove that a valid user from tenant A cannot list, retrieve, search, update, review or indirectly access tenant B data. Test every route and background worker, not only the policy helper.

## Provider selection gate

Choose a provider only after comparing: OIDC standards support, UK/EU data residency and contractual terms, MFA/passkey support, tenant/organisation modelling, account recovery, audit logs, SCIM or lifecycle provisioning, pricing at expected user counts, developer ergonomics, availability, exportability and exit strategy.

No vendor is selected by this document. Until selection and implementation are reviewed, proposal review remains HTTP 503 and the platform must not claim verified user identity or tenant isolation.


## Implemented composition seam (not an authenticator)

The branch now contains `atlas_engine/verified_identity.py` with a minimal immutable `VerifiedIdentity(issuer, subject)` value and `principal_from_verified_identity(...)`. The composition function resolves the identity through the isolated server-side membership registry and creates the immutable `RequestPrincipal` from the returned tenant and scopes. Unknown, revoked, inactive or ambiguous memberships fail closed.

This is deliberately only the seam between a future token verifier and the registry. The value type can be instantiated by Python code, so it is not cryptographic proof and must never be populated from request data. Until the real verifier and server-only composition wiring exist, the proposal-review route remains disabled and no HTTP endpoint may accept this object from a client.

## Implemented local scope policy (still not an authenticator)

`atlas_engine/scope_policy.py` now provides a closed local role-to-scope map for the future verifier adapter. The starter `atlas_viewer` role grants read-only scopes; `atlas_operator` grants the bounded task, evaluation, lesson and proposal read/write scopes. Unknown roles grant nothing, malformed role claims fail closed, and proposal-review permission is deliberately absent. The mapper accepts verified provider roles only; it has no input for client-requested scopes.

This mapping is a conservative engineering starting point, not a final production role model. The selected identity provider's role/group claims, tenant administrator lifecycle, break-glass policy and separation-of-duties model must be reviewed before activation. The map must remain server-controlled and must not be overridden by tenant payloads.

## Tenant membership administration and actor-attributed audit

The branch now includes `atlas_engine/tenant_admin.py`, a narrow server-side façade for provisioning and revoking a member within the acting administrator's own tenant. It requires an immutable `RequestPrincipal`, active membership, and the reserved `tenant:members:manage` scope. The target tenant is always taken from the principal; the façade exposes no caller-supplied tenant selector. The new scope is allowlisted for policy validation but is deliberately not granted to the starter viewer or operator roles.

Membership provision/revoke audit events can now record the acting principal's issuer and subject. The registry's lower-level provisioning methods remain bootstrap primitives and may still create events with NULL actor fields; production administrative operations must use the façade after a real trusted identity adapter is deployed. The Python object boundary is not cryptographic authentication, and this change does not enable any HTTP admin endpoint or select an identity provider.


## Provider-neutral verifier contract and selection gate

The branch now defines `atlas_engine/oidc_contract.py`:

- immutable deployment configuration with exact issuer, API audience, HTTPS JWKS URI, explicit algorithm allowlist and bounded clock skew;
- a `TokenVerifier` protocol for the future cryptographic adapter;
- a minimal immutable `VerifiedTokenClaims` output contract;
- a second-stage issuer/audience/claim-shape check before membership resolution.

`atlas_engine/oidc_composition.py` composes the trusted verifier output with the server-side membership registry. Provider role strings are not permissions at request time; the registry's server-controlled membership scopes remain authoritative. This prevents token-supplied role text from silently escalating a tenant membership.

These modules do not verify signatures, fetch JWKS, validate token time claims against a live clock, or authenticate bearer tokens. No production verifier or FastAPI dependency is wired. The typed claim object can be instantiated by Python code, so it must only be returned by the future trusted verifier and must never be built from HTTP input.

### Provider evaluation scorecard

Before selecting a vendor, evaluate each candidate against the same evidence checklist:

| Criterion | Required evidence |
| --- | --- |
| OIDC conformance | Exact issuer/audience behaviour, supported flows, discovery and JWKS rotation |
| Signing security | Algorithm controls, key rollover, unknown-key and JWKS outage behaviour |
| MFA and passkeys | Enforceable tenant policy, recovery controls and phishing-resistant options |
| Organisation model | Multiple organisations per identity, invitations, deactivation and membership lifecycle |
| UK/EU data handling | Contractual residency options, subprocessors, retention and transfer terms |
| Audit and operations | Admin audit export, security events, alerting and incident support |
| Enterprise lifecycle | SCIM or equivalent provisioning/deprovisioning, role/group claim controls |
| Commercial fit | Free/developer tier, production pricing, MAU/user limits and enterprise costs |
| Portability | Standards-based export, custom domain/issuer options and practical exit plan |

No provider is selected by this scorecard. A decision requires current vendor evidence, expected user volumes, budget and legal/data-processing review. Keep the application provider-neutral until that comparison is complete.


## Implemented HTTP bearer boundary (adapter still unconfigured)

`atlas_engine/http_identity.py` now provides a FastAPI dependency and immutable
`VerifiedIdentityService` composition object. It accepts only a bounded
Authorization bearer header, delegates cryptographic verification to the
configured `TokenVerifier`, rechecks issuer/audience and token time claims,
then resolves the subject through the server-side membership registry.
Client-supplied tenant, role and scope fields are not read. Multiple active
memberships are rejected rather than guessed. Raw tokens and verifier details
are not returned in HTTP errors or logged by this boundary.

The dependency returns HTTP 503 when no `VerifiedIdentityService` is installed,
HTTP 401 for invalid credentials or membership, and HTTP 503 for an explicitly
reported verifier outage. A deployment must install the service through
server-side application configuration; it must never be populated from a
request body or environment values containing raw user tokens.

This is an integration primitive, not a live login system. There is still no
cryptographic verifier implementation, configured issuer/JWKS, HTTP route
using this dependency, login/callback/session flow, or tenant-aware conversion
of the existing global application routes. Existing proposal review remains
disabled. Do not describe the application as having verified-user
authentication or production tenant isolation until those remaining pieces
and the route-by-route data migration have been implemented and tested.


## Cryptographic verifier and opt-in application wiring

The branch now includes `atlas_engine/oidc_jwt_verifier.py`, implemented with
pinned `PyJWT[crypto]`. It obtains signing keys only from the deployment's
configured HTTPS JWKS URI, restricts verification to the configured algorithm
allowlist, and verifies the signature, exact issuer, API audience, expiry and
not-before claims. It requires `exp`, `nbf`, `iss`, `sub` and `aud`; validates
the returned claim types; and enforces `azp` when multiple audiences are present.
JWKS transport failures are distinguished from rejected/unknown signing keys.
The JWKS client uses a bounded five-second timeout and a five-minute key-set
cache, with PyJWT's key-refresh behavior for unknown key IDs.

The FastAPI composition root now builds this verifier only when all five
deployment settings are present:

- `ATLAS_OIDC_ISSUER` — exact configured issuer
- `ATLAS_OIDC_AUDIENCE` — this API's audience
- `ATLAS_OIDC_JWKS_URI` — trusted HTTPS signing-key endpoint
- `ATLAS_OIDC_ALLOWED_ALGORITHMS` — explicit comma-separated algorithm allowlist
- `ATLAS_MEMBERSHIP_DB_PATH` — server-controlled membership database path

If any setting is missing or configuration is invalid, verified identity
remains disabled. The isolated membership registry is initialized at that
configured path; membership provisioning remains a trusted administrative
operation and there is no public provisioning endpoint.

`GET /identity/me` is the first route protected by the verified bearer
principal. It returns only the authenticated issuer, subject, tenant and
server-assigned scopes. This is an integration diagnostic endpoint, not a
substitute for tenant-aware application routes. Existing global task/source/
proposal routes are not yet tenant-scoped, and proposal review remains
disabled. Do not attach the dependency to those routes until their storage
ownership and tenant predicates are migrated and tested.

The verifier and configuration tests use generated RSA keys and injected JWKS
clients; they do not call a real identity provider or prove a production
provider's discovery, key rotation, login, callback, refresh, logout, MFA or
session behavior. Provider selection and real deployment configuration remain
explicit gates. Do not add real issuer secrets or tokens to the repository.


## First tenant-scoped Professor route

`GET /professor/tenant/plans/{plan_id}` is now the first application route
behind the verified-principal dependency. It reads only the isolated tenant
plan database configured by `ATLAS_TENANT_DATA_DB_PATH`, composes the
tenant-aware plan and step repositories with the Professor inspection
facade, and returns a bounded observational report. It does not dispatch,
resume, execute or retry steps. A caller without `plans:read` or
`steps:read` is denied; a plan belonging to another tenant is returned as
not found. The endpoint does not use the shared API key as a substitute for
human identity.

The tenant plan database is deliberately separate from both the legacy core
task database and the membership database. Its schema is initialized only
when the deployment supplies the dedicated path. Existing global task,
source, proposal and learning routes remain on their existing boundary and
must not be treated as tenant-isolated. The empty application capability
catalogue also means readiness previews will block unknown capabilities;
that is intentional until trusted capability definitions are registered.


`POST /professor/tenant/plans` now accepts a bounded plan description from a
verified tenant principal with `plans:write`. The request schema rejects
unknown fields, bounds the plan to 64 steps and validates the existing typed
Professor plan contract (dependency graph, risk classes, scopes, timeouts and
resource budgets). The server generates the plan ID and persists only a
`DRAFT`. The request cannot supply a tenant ID, state, approval reference,
worker identity or execution result. Creation never approves or executes work.


## Policy-gated tenant plan preparation

`POST /professor/tenant/plans/{plan_id}/prepare` is the next lifecycle boundary.
It accepts only a verified tenant principal and a plan currently in `DRAFT`.
The server loads the tenant-owned plan, constructs a temporary `READY` candidate,
and runs the central non-executing Professor policy preview against the trusted,
application-owned capability catalogue and the principal's server-assigned
scopes. The persisted plan transitions to `READY` only when every step is
structurally eligible. Missing/ambiguous capabilities, risk mismatches,
missing scopes, blocked dependencies and unverified approval requirements
leave the plan in `DRAFT` and return bounded readiness reasons.

The capability catalogue is currently empty by default. Until trusted
application-owned capability definitions are deliberately registered, plans
will remain drafts with unknown capabilities blocked. Client plan payloads
cannot register capabilities or change the catalogue. The same configured
catalogue is used by plan inspection so the report agrees with preparation.

This route does not approve a plan, issue a worker lease, dispatch a handler,
execute local or external work, or enable retries. External-side-effect and
privileged steps remain blocked because action-bound verified human approval
has not yet been implemented. A `READY` state means only that the current
metadata and policy checks passed; it is not permission to execute.


## First bounded Professor execution capability

The application now installs a trusted, immutable capability runtime containing
one handler: `math.calculate@1.0.0`. It accepts a bounded arithmetic expression
and evaluates it using the existing AST-based local arithmetic evaluator. It
does not use a shell, execute Python supplied by a caller, access the network,
write external systems or invoke paid AI services. The capability is classified
as `local_computation`, has a ten-second ceiling, validates both input and
output against its registered JSON Schemas, and requires the server-assigned
`compute:local` scope.

A verified tenant operator with `plans:execute`, `plans:write`,
`steps:claim`, `steps:complete`, `steps:read` and `compute:local` may call
`POST /professor/tenant/plans/{plan_id}/execute-next`. The route rechecks the
central plan preview, transitions an eligible READY plan to RUNNING, claims
exactly one dependency-ready step with a fenced lease, invokes only the
application-owned handler, and persists the bounded result or a generic failure
code. Repeated calls advance one step at a time; the plan becomes SUCCEEDED
only after every step is recorded as succeeded. A failed or expired attempt is
not automatically replayed.

For this initial vertical slice, `math.calculate` treats the step's
`objective` field as the arithmetic expression (for example, `2 + 2`). It is
a deliberate proving-ground capability, not yet a general natural-language
planner or research executor. External-side-effect and privileged capabilities
remain blocked; no approval bypass, arbitrary plugin loader, network handler,
production identity provider or deployment is introduced.


## First source-attributed research capability

The trusted capability catalogue now also includes
\`research.crossref.search@1.0.0\`. It uses the existing Crossref public
bibliographic metadata adapter, which performs bounded HTTPS GET requests to
Crossref's fixed API host. It retrieves at most three scholarly records per
step and returns each record's title, DOI URL, publisher, retrieval timestamp
and available abstract. It does not fetch full text, access private material,
write to the knowledge library or invoke a paid AI service.

A plan step uses its objective as the search query and must declare the
\`research:public\` scope. The runtime supplies the result limit itself; the
plan cannot raise it. The response schema validates the returned shape and
bounds each field. Retrieved abstracts and metadata are explicitly labelled
untrusted source material. A citation URL records provenance; it is not a
claim that the paper's findings have been independently validated.

The normal Professor execution route is reused: the plan must pass readiness
checks, a verified tenant principal must have \`plans:execute\` and the
capability's required scope, one dependency-ready step is claimed, and its
source-attributed result is stored in the tenant step record. No arbitrary URL
fetching, summarisation claim, source approval, external write or automatic
retry is introduced. The next research increment should add evidence
normalisation and cross-source comparison while preserving per-claim source
links and uncertainty.
