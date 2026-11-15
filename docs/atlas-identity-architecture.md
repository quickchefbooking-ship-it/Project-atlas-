# Atlas Identity — architecture decision and staged build

Status: **Approved direction; implementation not yet enabled**

## Decision

AtlasOnePro will own its application identity, organisation membership, authorisation,
session policy and security audit model. An external identity provider such as Auth0
may be used temporarily as an optional authentication front end, but it must not
become the source of truth for Atlas tenant membership, permissions, or customer data.

The product is not in a hurry to launch. Build and verify this subsystem in isolated
stages. Do not enable customer registration or production sign-in until the security
acceptance criteria below are met.

## Separate the identity concepts

Atlas Identity has four distinct responsibilities:

1. **Authentication** — establish that a person controls an account using a
   supported credential (initially email plus password; passkeys and MFA later).
2. **Account lifecycle** — registration, email verification, recovery, credential
   rotation, account suspension and account deletion workflows.
3. **Organisation membership** — associate an account with one or more Atlas
   organisations, with explicit invitation and acceptance.
4. **Authorisation** — derive tenant and capability permissions from Atlas-owned
   membership records. Never trust roles, tenant IDs or permissions supplied by a
   browser or copied from an external identity-provider claim.

An external OIDC provider proves an upstream identity only. It does not grant Atlas
access by itself.

## Existing foundations to reuse

The repository already contains:
- a pinned-issuer/JWKS JWT verifier and provider-neutral OIDC contract;
- immutable verified request principals and fail-closed tenant/scope checks;
- a server-controlled SQLite tenant membership registry;
- explicit membership revocation and minimal membership audit events;
- tenant/owner-isolated Professor conversation storage.

These are foundations, not a complete user-facing identity product. The existing
manual bearer-token entry in Professor chat is a controlled development bridge,
not an acceptable customer login experience.

## Target architecture

- **Account store:** Atlas-owned account IDs, normalized email addresses, account
  status and timestamps. Password material is stored only as a modern one-way
  password hash, never plaintext or reversible encryption.
- **Credential service:** use a maintained password-hashing library with a
  memory-hard algorithm (Argon2id preferred). Parameters must be benchmarked and
  versioned; support rehash-on-login. Never implement cryptography ourselves.
- **Verification and recovery:** single-use, random, high-entropy tokens; store only
  token hashes; short expiry; invalidate on use; rate-limit requests; responses must
  not disclose whether an email is registered.
- **Sessions:** opaque, random session identifiers; server-side session records;
  Secure, HttpOnly, SameSite cookies; rotation after authentication and privilege
  changes; idle and absolute expiry; server-side revocation. Do not put access or
  refresh tokens, credentials, or session state in localStorage, URLs, or readable
  cookies.
- **CSRF and browser protection:** CSRF protection for cookie-authenticated state
  changes, strict Origin/Host validation, HTTPS-only production cookies, restrictive
  security headers and a documented CORS allowlist.
- **Organisation model:** invitation-based membership, explicit acceptance,
  tenant isolation, least-privilege roles mapped to Atlas scopes, independent
  membership suspension/revocation and audit events.
- **MFA and passkeys:** add after the secure account/session lifecycle is proven.
  Prefer WebAuthn/passkeys and TOTP with recovery codes; never use SMS as the only
  second factor for privileged accounts.
- **Operations:** migration and backup strategy, secret management, key rotation,
  abuse/rate-limit monitoring, retention and deletion policy, incident response,
  security logging without secrets, and account-support procedures.

## Staged implementation plan

### Stage A — design and boundary (current)
- Record this architecture decision.
- Keep all identity routes fail-closed unless verified identity is configured.
- Keep tenant membership and permissions server-controlled.
- Document the distinction between identity-provider readiness and actual login.
- No public registration, passwords, sessions, or production identity endpoints.

### Stage B — account and credential core
- Add isolated account schema and migration tests.
- Add account repository and password-hash service using a maintained Argon2id
  implementation.
- Add generic registration validation and verification-token storage primitives.
- Test duplicate email races, password handling, token single-use/expiry, timing-safe
  comparisons where applicable, and absence of secrets in logs/responses.
- Do not expose public routes yet.

### Stage C — session and browser security
- Add server-side opaque sessions, secure cookie policy, CSRF protection, session
  rotation, expiry and revocation.
- Add adversarial tests for fixation, replay, CSRF, origin mismatch and logout.
- Keep the bearer-token development bridge isolated and clearly marked.

### Stage D — account lifecycle and organisation onboarding
- Add verified email flow, recovery, invitations, acceptance, account suspension
  and membership revocation.
- Add per-IP and per-account rate limits and generic public responses.
- Ensure all account and membership changes create minimal security audit events.

### Stage E — MFA, passkeys and operational readiness
- Add MFA/passkeys and recovery flows.
- Add backup/restore and key-rotation exercises, retention/deletion controls,
  monitoring, incident runbooks and independent security review.
- Complete penetration testing and deployment review before enabling customers.

## Security acceptance criteria

No stage is complete solely because its happy-path test passes. Required coverage
includes:
- unauthenticated and unverified identities fail closed;
- one organisation cannot read, mutate or infer another organisation's records;
- client-supplied tenant IDs, roles and scopes never establish authority;
- password hashes and one-time token hashes are never returned or logged;
- expired, reused, revoked and malformed credentials are rejected;
- sessions rotate after login and privilege changes and can be revoked server-side;
- cookie-authenticated mutations reject invalid/missing CSRF tokens and untrusted
  origins;
- rate limits prevent credential stuffing, enumeration and recovery abuse;
- account deletion and retention behaviour is explicit and tested;
- audit events identify the action and actor without recording secrets;
- dependency, migration, backup/restore and deployment configuration are reviewed.

## Cost and provider policy

Prefer maintained open-source components and existing infrastructure. No paid
identity service is required to design or build Atlas-owned account and membership
logic. Email delivery, hosting, databases and security monitoring may incur costs
when activated; disclose and approve those before use.

Auth0 Free can remain an optional temporary OIDC provider for development or
customer trials, but do not build Atlas permissions around Auth0-specific roles or
organisation IDs. Do not create a provider tenant, activate billing, add secrets,
or deploy authentication without explicit owner approval.

## Explicit non-goals for this stage

- No production login or registration is enabled.
- No passwords, email addresses or customer credentials are collected.
- No Auth0 account or paid service is provisioned.
- No deployment, database migration or secret configuration is performed.
- No claim of SOC 2, ISO 27001, Cyber Essentials or UK GDPR certification is made.
  This architecture supports preparation; formal compliance requires operational
  controls, evidence and independent assessment.
