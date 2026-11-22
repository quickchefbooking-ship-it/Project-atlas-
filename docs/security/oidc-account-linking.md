# Explicit OIDC-to-Atlas account linking

atlas_engine/oidc_account_link.py provides a repository and service boundary
for mapping a cryptographically verified external OIDC subject to an existing
Atlas account. It does not add HTTP routes or enable public login.

## Linking an identity to an existing account

A trusted future linking route must:

1. Authenticate the current browser request with the existing Atlas-owned
   session and session-bound CSRF checks.
2. Obtain the immutable RequestPrincipal from the server-side session service.
3. Require the server-provisioned identity:link scope.
4. Start and consume a one-time OIDC PKCE transaction.
5. Exchange the authorization code using the server-held verifier and verify
   the ID token with the deployment-pinned issuer, JWKS URI, algorithm allowlist
   and registered browser client ID.
6. Pass the verified claims and consumed transaction to
   OIDCAccountLinkService.link_authenticated_account; the service compares
   the verified nonce with the transaction's stored nonce digest.
7. Never accept an account ID, issuer, subject, tenant, role, scope or email
   supplied by the browser as proof of identity or authorization.

The Atlas account ID comes only from the authenticated Atlas principal. The
account must still be active when the mapping is written.

## Login resolution

A future OIDC callback uses OIDCAccountLinkService.resolve_login_account only
after consuming the one-time state, exchanging the code and verifying the ID
token. The service checks the nonce binding and resolves an exact
(issuer, subject) mapping. It rejects unknown identities and inactive Atlas
accounts.

There is deliberately no email-based account matching or automatic account
creation. Provider email, profile claims, roles and tokens are not persisted.
The mapping is unique by (issuer, subject) and by (account_id, issuer), so one
external identity cannot be reassigned and one Atlas account cannot silently
accumulate multiple subjects from the same issuer.

## Storage and audit

The additive atlas_oidc_account_links table shares the dedicated Atlas
account database and has a foreign key to atlas_accounts. A minimal
atlas_oidc_account_link_events row is written in the same transaction as a
new link. The repository must be initialized explicitly after the account
schema; no migration is applied automatically at application startup.

The event table is application-level audit evidence, not tamper-proof storage.
Production use still requires reviewed migrations, database access controls,
backups, retention and operational monitoring.

This is not a complete hosted sign-in flow. Provider selection, deployment
configuration, callback routes, token exchange, Atlas session issuance,
logout/revocation and real-provider end-to-end verification remain outstanding.
