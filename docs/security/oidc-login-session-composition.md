# OIDC login to Atlas browser-session composition

`atlas_engine/oidc_login_session.py` composes the existing OIDC account-link
service with Atlas-owned tenant membership and opaque browser-session
repositories. It is a provider-neutral service boundary, not an HTTP route.

## Completion sequence

A future callback handler must first:

1. Consume the one-time authorization state from the PKCE transaction store.
2. Exchange the authorization code using the stored verifier.
3. Verify the ID token with the deployment-pinned issuer, JWKS endpoint,
   algorithm allowlist and registered browser client ID.
4. Pass the verified claims and consumed transaction to
   `OIDCLoginSessionService.complete_login`.

The service then:

1. Resolves the exact, previously linked issuer/subject pair and checks the
   consumed transaction nonce.
2. Resolves the internal Atlas account ID only from that explicit mapping.
3. Requires exactly one active Atlas tenant membership from the server-owned
   membership registry. Missing, inactive or ambiguous memberships fail closed.
4. Issues an opaque Atlas session in the same account database used by the
   account-link repository.
5. Re-authenticates the new session through the existing membership service
   and rejects tenant or scope changes that occur during issuance.
6. Issues a session-bound CSRF token.
7. Revokes the newly created session if membership revalidation or CSRF
   issuance fails.

The returned session and CSRF credentials are redacted from the result
representation. Trusted callback code receives them only so it can establish
the approved browser response; this module does not set cookies or return an
HTTP response.

## Security boundaries and remaining work

- No email-based matching, automatic account creation, provider-role mapping,
  browser-supplied tenant selection or browser-supplied account ID.
- No provider discovery, arbitrary JWKS URL, authorization-code exchange,
  HTTP routes, cookie attributes, logout route or public-login enablement.
- The callback must still enforce state/nonce/PKCE, exact redirect URI,
  trusted origin and secure cookie policy.
- Tenant membership remains server-controlled and is rechecked after session
  creation and on every authenticated browser request.
- Session issuance and the separate membership database cannot share one
  SQLite transaction. A detected membership change causes the just-issued
  session to be revoked; later requests independently re-resolve membership.
- Production database migration, key provisioning, backup/restore, operational
  monitoring and real-provider end-to-end verification remain outstanding.

This component is not evidence that hosted login is live or that the Replit
deployment has been updated.
