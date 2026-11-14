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
