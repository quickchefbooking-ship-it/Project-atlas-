# Hosted OIDC browser routes

## Scope

The hosted browser router exposes a fixed Authorization Code + PKCE initiation
route, a one-time callback route, and an authenticated logout route. It is
provider-neutral: deployment-owned startup code must inject the authorization
initiator and callback service. Missing services return 503; the router never
selects a provider or discovers endpoints from browser input.

## Login initiation

The initiator uses a deployment-pinned HTTPS authorization endpoint, registered
client ID and exact HTTPS callback URI. It creates state, nonce and an S256 PKCE
challenge through the encrypted server-side transaction store. Only the
challenge, state and nonce are sent to the provider. The verifier remains in
server-side storage. The requested scope is intentionally limited to openid;
Atlas account linking does not rely on provider email claims.

## Callback and cookies

The callback consumes provider error responses as well as successful state
values. A successful callback delegates code exchange, ID-token verification,
explicit account linking and Atlas session issuance to the existing services.
The browser receives a 303 redirect to the fixed Professor chat page.

The Atlas session is set only in a Secure, HttpOnly, Path=/, host-only
__Host-atlas_session cookie. The session-bound CSRF token is placed in a
Secure, same-site, host-only __Host-atlas_csrf cookie readable by same-origin
application code, which must echo it in X-Atlas-CSRF. Unsafe cookie-authenticated
requests still require the exact server-configured Origin and session-bound
CSRF validation.

Logout is a POST protected by the existing verified-principal dependency. It
revokes the current server-side session and clears both cookies.

## Remaining launch requirements

The router does not create or provision identity-provider credentials, database
paths, the dedicated 32-byte transaction-encryption key, or a provider token
endpoint client. The application startup composition and browser UI still need
to be connected to these services. Route registration is not proof of a live
provider round trip. Public login must remain disabled until deployment
configuration, real-provider testing, browser-session tests and operational
review are complete.
