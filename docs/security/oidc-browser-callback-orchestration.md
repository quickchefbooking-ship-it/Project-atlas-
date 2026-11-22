# OIDC browser callback orchestration

## Scope

The atlas_engine.oidc_browser_login service composes the existing server-side OIDC and Atlas identity primitives into one callback operation:

1. Consume the unpredictable OIDC state through the encrypted, one-time PKCE transaction store.
2. Exchange the authorization code using the recovered server-held PKCE verifier and a fixed deployment-owned redirect URI.
3. Verify the returned ID token through the pinned issuer/JWKS verifier.
4. Resolve only an explicit issuer/subject-to-Atlas-account link.
5. Require the existing Atlas session service to confirm one active server-provisioned tenant membership.
6. Issue the opaque Atlas session and its session-bound CSRF token.

The callback and account-link services must share the exact same transaction-store instance. This ensures the nonce check is bound to the state that the callback consumed.

## Security boundaries

- State is consumed before the provider exchange. Exchange, verification, account-link or membership failures cannot make a transaction reusable.
- The PKCE verifier is passed only from server-side storage to the trusted exchanger. It is never returned in a browser response.
- The redirect URI is fixed when the service is constructed. Callback input cannot select a host or redirect destination.
- The token response is accepted only from the trusted adapter, with bounded ID/access tokens and bearer token type.
- The ID token is verified for the registered browser client by the pinned verifier; an API bearer token is not substituted.
- The existing account-link/session services recheck nonce, active account, unique tenant membership and CSRF issuance.
- Token and session credentials are excluded from the relevant dataclass representations. Provider exception text is not propagated from the code-exchange boundary.
- No provider email, role, tenant, account ID or permission is accepted from callback parameters.

## Deliberate limitations

This is a provider-neutral orchestration service, not a hosted login route. It does not perform discovery, HTTP token exchange, authorization redirects, cookie handling, logout, provider registration or deployment configuration. A later HTTP adapter must use deployment-pinned HTTPS endpoints and client settings, map errors to generic responses, set the __Host-atlas_session cookie with Secure, HttpOnly, Path=/ and an appropriate SameSite policy, and expose the CSRF token only through the intended same-origin mechanism.

The service does not prove that a live identity provider is configured or that a Replit deployment has changed. Public login remains disabled until the complete route, provider round trip, deployment secrets and operational checks are separately reviewed.
