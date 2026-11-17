# Hosted OIDC browser routes

## Scope

The hosted browser router exposes a fixed Authorization Code + PKCE initiation
route, a one-time callback route, and an authenticated logout route. It is
provider-neutral: deployment-owned startup code must inject the authorization
initiator and callback service. Missing services return 503; the router never
selects a provider or discovers endpoints from browser input.

## Login initiation and browser binding

The initiator uses a deployment-pinned HTTPS authorization endpoint, registered
client ID and exact HTTPS callback URI. It creates state, nonce and an S256 PKCE
challenge through the encrypted server-side transaction store. Only the
challenge, state and nonce are sent to the provider. The verifier remains in
server-side storage. The requested scope is intentionally limited to openid;
Atlas account linking does not rely on provider email claims.

The route also sets a short-lived Secure, HttpOnly, SameSite=Lax host-only
__Host-atlas_oidc_state cookie. The callback must present the same state in the
query and cookie, compared in constant time. This binds the callback to the
browser that initiated login and prevents a copied callback URL from silently
signing another browser into the attacker's Atlas account. A mismatched browser
does not consume the legitimate transaction.

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
CSRF validation. The temporary state cookie is cleared after a valid callback.

The Professor chat page now prefers the Atlas cookie session, sends the CSRF
header for unsafe same-origin requests, attempts a session connection on page
load, and uses the protected logout route. The temporary bearer-token bridge
remains available for controlled testing and is not persisted in browser storage.

Logout is a POST protected by the existing verified-principal dependency. It
revokes the current server-side session and clears the session, CSRF and
temporary OIDC state cookies.

## Remaining launch requirements

The application now has a fail-closed startup factory that builds the matching
authorization initiator and callback services only when the complete set of
deployment-owned settings is present. It requires pinned issuer, JWKS,
authorization and token endpoints; a registered browser client and exact
`/identity/callback` redirect URI; a dedicated 32-byte transaction-encryption
key; and separate file-backed account, membership and transaction databases.
The optional client secret is used only for a confidential client; public
clients rely on PKCE.

Startup creates empty schemas only. It does not create Atlas accounts, external
identity links, tenants or tenant memberships. Each external identity must
already have an explicit account link, and the Atlas account must have one
active server-provisioned membership under the Atlas identity issuer. No
email-based matching or automatic provisioning is performed.

The readiness endpoint now lists missing setting names and distinguishes
invalid configuration, unconfigured services and a configured-but-unverified
login flow. It never returns endpoint values, client secrets or key material.
Configuration presence and service construction are not proof of a live
provider round trip. Public login must remain disabled until deployment
settings, real-provider testing, browser-session tests and operational review
are complete. No Replit deployment settings or secrets are changed by this
code change.
