# OIDC login transaction store

The provider-neutral login transaction primitive is implemented in
`atlas_engine/oidc_login_transaction.py`. It is deliberately not wired to
HTTP routes and does not make hosted login ready.

## Contract

- `begin()` generates unpredictable state and nonce values plus a PKCE
  verifier and its S256 challenge.
- The state and nonce are stored only as keyed digests.
- The PKCE verifier is encrypted at rest with AES-256-GCM. The store derives
  separate HMAC and encryption keys from a dedicated 32-byte deployment key.
- `consume(state)` uses an immediate SQLite transaction to claim a callback
  exactly once. Expired, unknown and replayed states fail with the same
  bounded error.
- Consumption is committed before verifier decryption, so corrupted ciphertext
  cannot make a transaction reusable.
- `nonce_matches` compares a verified ID-token nonce to the stored digest in
  constant time.
- The default transaction lifetime is five minutes and is bounded to 60–900
  seconds.

## Future route integration

A future server-side login route may call `begin()`, send only state, nonce and
the S256 challenge to the configured provider, and keep the verifier inside
trusted server code. The callback must call `consume(state)` before exchanging
the authorization code, use the returned verifier for the token request, verify
the ID token with the configured OIDC verifier, and check the verified ID-token
nonce with `nonce_matches`. Only then may it resolve the server-controlled
tenant membership and issue an Atlas-owned session.

The verifier must never be placed in a browser URL, response, cookie, or log.
The database path must be dedicated and protected by deployment filesystem
permissions. The 32-byte key must come from deployment secret management, be
stable across application instances, and never be committed to the repository.
Losing or rotating the key invalidates outstanding login transactions.

This module does not perform provider discovery, validate issuer/redirect
allowlists, exchange codes, verify ID-token signatures, choose a tenant,
create sessions, set cookies, or implement logout. It does not enable public
login. The readiness endpoint must continue to report hosted login as
unimplemented until the complete route and real-provider round trip are tested.
