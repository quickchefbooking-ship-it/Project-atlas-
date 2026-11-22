# OIDC ID-token verification

The new module atlas_engine/oidc_id_token_verifier.py adds a dedicated verifier
for OIDC ID tokens. It is separate from PyJWTTokenVerifier, which validates API
bearer tokens. An ID token is intended for the registered browser client, so
the verifier receives the OIDC client ID separately from the API audience in
OIDCProviderConfig.

The verifier:

- Uses only the deployment-pinned issuer, JWKS URI and algorithm allowlist.
- Requires and validates signature, issuer, client audience, expiry, issued-at,
  subject and a bounded nonce.
- Requires a matching azp when multiple audiences are present and rejects a
  mismatched azp.
- Validates at_hash against the token-endpoint access token when the ID token
  contains that claim.
- Returns a typed claim object whose nonce is excluded from its representation.

After signature verification, trusted callback code must compare the returned
nonce to the consumed login transaction with
SQLiteOIDCLoginTransactionStore.nonce_matches. The raw nonce must not be
accepted from browser-supplied data or written to logs. State consumption
remains one-time and must occur before code exchange.

This is a provider-neutral verification component only. It does not discover a
provider, fetch arbitrary JWKS URLs, exchange authorization codes, register
routes, create tenant memberships, issue Atlas sessions, or enable public login.
The configured browser client ID and trusted issuer/JWKS settings must come
from deployment-owned configuration. The live callback must still be tested
against the selected provider before readiness can advance.
