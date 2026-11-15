# Atlas Identity — browser session and authentication boundary

## Status

This is an implementation boundary and security checklist, not a declaration that browser login is live. Account credentials, one-time account tokens and server-side session primitives exist in the backend. Public registration, login, logout and email delivery remain disabled until the controls below are implemented and tested together.

## Current backend guarantees

- Passwords are hashed with Argon2id; plaintext passwords are not persisted.
- Email verification and password-recovery tokens are random, single-use, expiring, and stored as SHA-256 digests.
- Session credentials are opaque random values; only their SHA-256 digests are persisted.
- Sessions have bounded idle and absolute expiry.
- Session validation checks current account status.
- Session rotation atomically retires the previous credential and preserves the original absolute expiry.
- Password reset revokes all sessions for the account.
- Suspending or closing an account revokes all existing sessions.
- Session/account primitives do not themselves create browser cookies or expose public authentication routes.

## Browser integration requirements before enabling sign-in

1. Use maintained, security-reviewed framework/library primitives where practical; do not hand-roll cryptographic protocols.
2. Serve authentication only over HTTPS. Reject insecure production configuration rather than silently weakening cookie policy.
3. Set an opaque session cookie with Secure, HttpOnly, SameSite=Lax (or stricter where compatible), Path=/, and no Domain attribute. Use a __Host- cookie name in production.
4. Never put credentials or session identifiers in URLs, HTML, JavaScript-readable storage, analytics, logs, or error messages.
5. Protect state-changing cookie-authenticated requests with CSRF tokens and strict Origin/Referer validation. SameSite is defence in depth, not the only CSRF control.
6. Apply login, registration, verification and recovery rate limits by account identifier and network source; use generic outward responses for unknown accounts and incorrect credentials.
7. Use constant-time-safe framework primitives where secret comparison is required. Never compare raw tokens in application code when a digest lookup can be used.
8. On successful login, issue a fresh session. Rotate after authentication and privilege changes. On logout, revoke server-side before clearing the cookie.
9. On password reset, revoke all sessions, invalidate outstanding recovery/verification tokens, and require fresh authentication.
10. Email verification/recovery delivery must use a configured, approved mail transport. Never return raw tokens from a public API or expose them in logs. Delivery links must use a configured canonical HTTPS origin, not an untrusted Host header.
11. Add security headers, restrictive CORS (same-origin by default), request-size limits, generic error handling and audit events without secrets.
12. Add integration tests for CSRF rejection, cookie attributes, origin validation, brute-force throttling, enumeration resistance, login/logout, session fixation, rotation, account suspension and password-reset revocation.

## Planned HTTP surface (not yet enabled)

- POST /identity/register — create a pending account; generic response; no session until verified.
- POST /identity/login — verify active account credentials and issue a new server-side session.
- POST /identity/logout — revoke current session and clear cookie.
- GET /identity/me — return minimal authenticated account identity and Atlas-owned memberships.
- POST /identity/email-verification/resend — generic response and throttled delivery.
- POST /identity/email-verification/confirm — consume a one-time verification token.
- POST /identity/password-recovery/request — generic response and throttled delivery.
- POST /identity/password-recovery/confirm — consume recovery token, change password, revoke all sessions.
- POST /identity/session/rotate — rotate the current session with CSRF and origin checks.

The exact route names are provisional until the API integration is reviewed. Do not register these routes merely by copying this document.

## Release gate

Do not enable public sign-in until all browser integration requirements and the corresponding automated tests pass, deployment secrets and canonical origin are configured, HTTPS and secure cookie behaviour are verified in the target environment, account recovery delivery is operational, and a human security review has approved the release. No certification (SOC 2, ISO 27001 or Cyber Essentials) is implied by these engineering controls.
