# Verified identity and tenant isolation — implementation plan

Status: design and policy primitives only. This document does not claim that AtlasOnePro currently has verified user identities or tenant isolation.

## Current state and security boundary

- The current HTTP dependency authenticates a shared `X-API-Key`; it does not identify an individual human reviewer.
- `ProposalReviewInput.approved_by` is caller-supplied audit metadata. It is not identity proof.
- `RequestPrincipal` is an immutable policy value intended to be constructed only by trusted server-side authentication code. There is currently no configured OIDC provider or middleware that can safely construct it.
- Core task, proposal, lesson and source records are not yet tenant-partitioned. The existing single-host SQLite store is not a multi-tenant isolation boundary.
- The new `authorize_proposal_review` policy requires an active `RequestPrincipal` with `lessons:review`. It is not yet wired into the review route.

## Required identity integration

Before enabling authenticated user sessions:

1. Select and configure an OIDC identity provider; record the approved issuer, client/audience, signing-key discovery endpoint and redirect URIs in deployment configuration.
2. Validate token signature against current issuer keys, exact issuer, audience, expiry, not-before and permitted algorithm. Reject missing, malformed, expired and wrong-audience tokens.
3. Resolve the subject's tenant membership from a server-controlled membership store. Never accept tenant IDs, roles or scopes as authority from request JSON or untrusted token claims unless the claim is explicitly issued and governed for this purpose.
4. Construct `RequestPrincipal` server-side only after all checks succeed. Keep the principal in request-scoped server context; never deserialize it from the request body.
5. Map provider roles to narrowly scoped application permissions. Proposal review requires `lessons:review`; membership must be active.
6. Fail closed when provider configuration, key retrieval, membership lookup or permission mapping is unavailable. Do not silently fall back to shared API-key identity for human review.

## Proposal-review route migration

- Preserve the current route as unavailable for human approval until verified identity is configured.
- Introduce a server dependency that returns a verified principal or denies the request.
- Resolve proposal tenant ownership from the database, not from request input.
- Authorize the principal against that tenant and `lessons:review` before changing status.
- Derive the reviewer audit subject from the verified principal's issuer and subject. Keep any display label separate from the immutable identity reference.
- Retain the existing atomic pending-to-reviewed transition to prevent concurrent double review.
- Add tests for missing/invalid token, wrong issuer/audience, expired token, revoked membership, missing scope, cross-tenant proposal, forged `approved_by`, and concurrent review.
- Do not enable approval or testing actions through the old shared-key route during migration.

## Tenant data migration

A separate reviewed migration is required before multi-tenant use:

1. Define tenant ownership and membership tables with stable IDs and foreign keys.
2. Add a non-null tenant ID to every tenant-owned task, attempt, evaluation, lesson, proposal, source document and related audit record.
3. Backfill existing records into an explicitly designated owner tenant; stop and require manual reconciliation if ownership is ambiguous.
4. Add tenant-scoped indexes and uniqueness constraints.
5. Require tenant predicates in every read, update and delete path; derive tenant from the verified principal, never the client.
6. Test cross-tenant list, get, search, update, review and indirect relationship access. Include negative tests for missing tenant IDs.
7. Do not claim isolation until all data paths, background workers, exports, logs and backups have been reviewed.

## Deployment and compliance gate

OIDC provider selection, secrets, callback URLs, production database migration, backup/restore, key rotation, monitoring and incident response require explicit deployment decisions and review. SOC 2, ISO 27001, Cyber Essentials and UK GDPR alignment are readiness goals, not certifications or proof of compliance. PCI DSS applies only if the product handles cardholder data.

## Current safe status

The pure reviewer policy is implemented and unit-tested. The live review route remains on its legacy shared-API-key boundary and must not be represented as verified-human authorization. No production tenant migration, identity provider, merge or deployment has been performed.
