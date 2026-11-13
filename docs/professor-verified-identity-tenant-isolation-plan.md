# Professor verified identity and tenant isolation — implementation plan

**Status:** design and migration plan only. No authentication provider, tenant model, database migration or route behaviour is changed by this document.

## 1. Current-state finding

The current API uses one optional shared `X-API-Key` gate for protected routes. When configured, it proves possession of the shared secret; it does not identify an individual, establish an organisation, grant role-specific scopes or isolate one customer's records from another's.

Several request models also accept caller-supplied attribution fields such as `actor`. Those values are useful as untrusted descriptions but must not be treated as proof of who performed an action. The current SQLite tables for tasks, attempts, lessons, proposals and source documents do not consistently carry a tenant boundary.

**Conclusion:** the current prototype is suitable only for controlled development/single-owner use. It must not be exposed as a commercial multi-user service or treated as a secure multi-tenant API.

## 2. Identity-provider decision gate

Do not hard-code a provider before deciding the product's account model. The implementation should use standards-based OpenID Connect (OIDC) authorization-code flow with PKCE for browser/mobile clients, or a documented server-to-server flow for trusted services.

Provider selection must be assessed against:
- UK/EU data residency and processor terms where relevant;
- MFA, account recovery, session revocation and audit capabilities;
- organisation membership and invitation workflows;
- support for short-lived access tokens and key rotation;
- iPhone Safari compatibility and secure redirect handling;
- pricing at the expected number of users and monthly active users;
- exportability and a credible migration path.

Do not build a home-grown password store or accept unsigned/self-issued JWTs. Validate token signature, issuer, audience, expiry, not-before, authorised algorithm and key ID using provider metadata/JWKS with safe key rotation. Never trust identity claims merely because a client sends them in JSON.

## 3. Server-side principal context

After successful authentication, middleware/dependency code should create an immutable request principal from verified claims and server-side membership lookup:

- `principal_id`: stable subject identifier scoped to the issuer;
- `issuer`: validated identity issuer;
- `tenant_id`: selected organisation, verified against active membership;
- `membership_status`: active/revoked/suspended;
- `roles`: resolved server-side role assignments;
- `scopes`: capability-specific permissions derived from role and policy;
- `auth_time` and `session_id`: where supplied and validated;
- `request_id`: server-generated correlation identifier.

Never accept principal, tenant, role or scope as authoritative from request bodies, query strings or custom headers. A client may request a tenant context, but the server must prove membership before creating the principal. Missing, ambiguous or revoked membership must fail closed.

## 4. Tenant data model

Before production multi-user use, every tenant-owned record must have a non-null `tenant_id`, including at minimum:
- tasks and task attempts;
- evaluations, lessons and improvement proposals;
- retry schedules, cancellation requests and recovery decisions;
- sources and source documents;
- capability approvals, execution events and audit records.

Use composite uniqueness and foreign-key relationships that include tenant ownership where possible. For example, a task reference from an attempt must resolve within the same tenant. Random IDs are not an authorisation mechanism.

All repository/storage methods must require a tenant context for tenant-owned records. Avoid convenience methods that fetch by bare ID. List, update, delete, count, search, dashboard and export queries must all include the tenant predicate. Background jobs must persist and revalidate the tenant context instead of reconstructing it from user-controlled data.

## 5. Safe migration sequence

Do not add nullable tenant columns and then quietly treat null as a shared tenant. Use a staged migration with a reviewed owner mapping:

1. **Inventory:** enumerate every table, query, API route, static dashboard and background operation that reads or writes persisted data.
2. **Ownership map:** explicitly map existing single-owner data to one designated owner tenant. Do not infer ownership from email text, actor labels or record contents.
3. **Backup and rehearsal:** create a restorable backup and rehearse migration against a copy; verify row counts, foreign keys and representative queries.
4. **Additive schema:** add tenant and ownership tables with indexes and constraints while the service remains single-owner/private.
5. **Backfill:** assign existing records only to the explicitly approved owner tenant; quarantine any record whose ownership is uncertain.
6. **Tenant-aware storage:** change every storage API to require a verified tenant context and enforce it in SQL, not only in route code.
7. **Negative tests:** prove cross-tenant access is denied for every entity and every operation, including indirect references and aggregate metrics.
8. **Enforce constraints:** only after backfill and tests pass, make tenant ownership non-null and enforce composite foreign keys/uniqueness.
9. **Controlled rollout:** enable authentication for a test tenant first; monitor denial events and query errors before any commercial release.

No migration should be run against production without a separate backup, rollback plan, explicit owner approval and a reviewed maintenance window.

## 6. Authorisation model

Start with a small deny-by-default role model, then grant narrow capability scopes. Suggested initial roles are:
- **owner:** manage organisation, members and policy; still cannot bypass action-specific safety gates;
- **admin:** manage approved users and non-security workspace settings;
- **operator:** create and inspect permitted tasks and approved source material;
- **reviewer:** review specified lessons, proposals and source documents;
- **viewer:** read only the records explicitly shared with them.

Roles are not a substitute for object-level checks. Every action must evaluate tenant membership, role, resource ownership, capability scope and risk policy. Sensitive administrative actions should require recent authentication or MFA where the provider supports it.

The shared API key may remain temporarily for local development or a tightly controlled service health probe, but it must not be the identity mechanism for user actions. It must be rotated and removed from public/client-side use before multi-user launch.

## 7. Audit and privacy

For every access or policy decision, record the verified issuer/subject, tenant, action, resource type/ID, decision, reason code, timestamp and request correlation ID. Do not log bearer tokens, API keys, passwords, full identity tokens or unnecessary personal data.

Define retention, export, correction and deletion processes before onboarding real users. A tenant deletion must cover primary records, derived indexes, cached data, backups according to documented retention, and any connected processor obligations. UK GDPR compliance cannot be claimed from implementing these controls alone; lawful basis, transparency, processor contracts, rights handling and operational evidence are also required.

## 8. Acceptance tests required before multi-tenant access

- unauthenticated, invalid-signature, wrong-issuer, wrong-audience, expired and not-yet-valid tokens are rejected;
- revoked users and suspended memberships lose access promptly;
- client-supplied tenant, principal, role and scope values cannot elevate privileges;
- tenant A cannot read, mutate, count, search, export or infer tenant B's records;
- cross-tenant task/attempt/evaluation/lesson/source references are rejected;
- every storage query and dashboard aggregate is tenant-scoped;
- background work revalidates tenant and membership policy;
- role and scope changes take effect without trusting stale client claims;
- shared-key-only user access is rejected outside the documented local development mode;
- audit events identify the verified principal and tenant without exposing secrets;
- migration rehearsal preserves valid records and quarantines uncertain ownership;
- rollback restores the pre-migration state without cross-tenant leakage.

## 9. Release gates

Verified identity and tenant isolation are prerequisites to capability dispatch, commercial onboarding and private customer data. A green unit-test suite alone is not sufficient. Require exact-commit CI, migration rehearsal evidence, security review, privacy review and explicit product-owner acceptance.

Until these gates pass, keep AtlasOnePro private/single-owner, keep specialist execution disabled and do not claim SOC 2, ISO 27001, Cyber Essentials or UK GDPR compliance.
