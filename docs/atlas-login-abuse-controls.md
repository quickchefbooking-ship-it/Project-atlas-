# Persistent login abuse controls

## Status

A reusable SQLite-backed throttling primitive is implemented and tested. It is
not yet connected to registration, login, verification, or recovery HTTP routes.
Public authentication remains disabled.

## Behaviour

- Counts failures in independent account-identifier and network-source buckets.
- Canonicalizes IPv4 and IPv6 address text before HMAC keying. Equivalent expanded
  and compressed IPv6 forms share a bucket, as do IPv4-mapped IPv6 and native
  IPv4 forms. Scoped IPv6 addresses and non-IP network identifiers are rejected.
- Uses atomic SQLite transactions so concurrent failures cannot silently bypass
  the configured threshold.
- Uses HMAC-SHA-256 keyed digests for bucket identifiers; raw email addresses and
  network addresses are not persisted in this table.
- Applies a bounded fixed window and temporary lockout, with configurable
  thresholds and durations.
- A successful login clears only the account bucket. It never clears the
  network-source bucket, preventing one successful account login from erasing
  broader network abuse history.
- Provides explicit expiry cleanup to bound retained bucket data.
- Fails closed at construction if a deployment secret of at least 32 bytes is
  not supplied.

## Integration gate

Before enabling public authentication, route integration must:
1. Load the HMAC key from deployment secret storage, never source control.
2. Use a trusted server-derived client IP address; do not trust arbitrary
   forwarded-for headers unless the proxy chain is explicitly configured.
3. Check both buckets before expensive password hashing/verification.
4. Record failures for unknown accounts and incorrect passwords identically.
5. Return generic outward errors and a bounded Retry-After header.
6. Clear only the normalized account bucket after successful credential checks.
7. Apply equivalent protections to registration, verification resend and
   password recovery; these routes need their own operation-specific policy.
8. Add end-to-end tests for concurrent requests, route enumeration resistance,
   proxy configuration, lockout and successful-login behaviour.

This module does not create login routes, send email, issue browser cookies, or
enable public sign-in. It is one prerequisite, not a release approval.
