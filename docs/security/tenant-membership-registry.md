# Server-controlled tenant membership registry

Status: isolated implementation and tests only. This is not connected to HTTP authentication, the existing Professor task database or production services.

## Purpose

The registry maps an already-verified identity pair (`issuer`, `subject`) to tenant membership and application scopes. It does not verify JWTs, accept browser-provided roles, or create `RequestPrincipal` instances.

## Data model

- `tenant_registry`: stable tenant ID, display name and active state.
- `tenant_memberships`: issuer + subject + tenant composite key, active state and server-provisioned scope set.
- `membership_audit_events`: append-only event records for tenant creation/deactivation/reactivation and membership provision/revocation. Events are committed in the same SQLite transaction as the corresponding change; failed changes do not leave success events.
- Audit details contain the target identity, tenant and scope changes, but never bearer tokens or raw identity claims.
- Foreign keys require membership to reference an existing tenant.
- Membership lookup fails for unknown identities, revoked memberships, inactive tenants and corrupt permission records.
- If an identity has multiple active tenant memberships, lookup fails as ambiguous unless a specific tenant is selected and independently matched against that identity's stored membership rows.

## Trust rules

- Only trusted provisioning/admin code may call tenant creation, membership provisioning, revocation or tenant activation methods.
- A token claim or browser payload cannot write membership rows or scopes.
- An explicit tenant selector is only a selector: the registry must prove the verified identity already belongs to that tenant.
- This component returns a membership record, not an authenticated principal. The future OIDC composition layer must first verify token signature, issuer, audience, time claims and API intent, then resolve membership, then map scopes and construct the request principal.
- Stored scopes must be provisioned by trusted server-side policy. Do not map arbitrary identity-provider groups directly to permissions.

## Operational limitations

- The registry is a small SQLite primitive for isolated development and tests.
- It uses a caller-supplied database path and does not modify `ATLAS_DB_PATH`.
- It is not yet suitable as a production multi-tenant control plane. Production requires reviewed database hosting, access control, encrypted backups, restore tests, migrations, audit trail, concurrency strategy, tenant lifecycle and administrative authorization.
- No route exposes these write methods. Do not add a public membership-provisioning route until admin identity and audit controls exist.
