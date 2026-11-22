# HTTPS OIDC token-exchange adapter

## Scope

The provider-neutral HTTPS exchanger implements the authorization-code
exchange contract consumed by the Atlas callback orchestration service. It
does not select an identity provider, perform discovery, verify ID tokens, map
accounts, issue sessions, or enable public login.

Trusted startup composition must provide one fixed token endpoint, registered
browser client ID and exact callback URI. The callback service continues to
supply the one-time authorization code and server-held PKCE verifier.

## Transport safeguards

- Token endpoint and redirect URI must be fixed HTTPS URLs without user-info,
  query strings, fragments or ambiguous control characters.
- TLS certificate verification remains enabled; the adapter exposes no
  insecure TLS override.
- Redirect following is disabled both on the HTTP client and the request.
- Environment proxy variables are not trusted by default.
- The request has a bounded timeout and the response is streamed under a
  configured byte limit.
- Only a successful JSON response with bounded ID/access tokens and Bearer
  token type is accepted.
- Duplicate JSON keys, non-JSON content, malformed responses and provider
  error bodies are rejected with generic errors.
- Authorization codes, PKCE verifiers, client secrets and returned tokens are
  never logged or included in exception representations.

## Client authentication

A public client sends its registered client ID in the form body and uses the
PKCE verifier. If a confidential client is selected, a client secret may be
passed separately to the adapter from deployment secret management. In that
case the adapter uses OAuth client_secret_basic and does not put the client ID
or secret in the form body. The secret is excluded from object representations.

No secret is stored in source control or added to the example environment
file. Provider-specific registration and authentication requirements must be
confirmed before startup composition is enabled.

## Remaining launch boundary

The adapter is a tested transport component, not proof of a real provider
round trip. Deployment startup still needs to compose the transaction store,
pinned verifier, account-link and session services, login-abuse protection,
and this exchanger using deployment-owned settings. Public login remains
disabled until a real provider test and operational review pass.
