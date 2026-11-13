# Lesson review and promotion governance

**Status: design only.** This document defines the safety gate for reusable lesson promotion. It does not add a review endpoint, change the database, or enable lesson validation.

## Current boundary

The Professor currently creates lessons with `validated=false` and retrieves only validated lessons. Lesson creation rejects attempts to self-validate. There is no supported lesson-review endpoint or durable lesson-review history.

The current API authentication model is a shared API key. Reviewer names and actor labels supplied by callers are audit metadata only; they do not prove a person's identity, role, organisation or authority. Therefore **no API caller may promote a lesson to reusable validated memory under the current model**.

Do not work around this boundary by editing the `validated` database column, adding an unauthenticated route, or treating a non-empty reviewer string as proof of authority.

## Required review lifecycle

A future implementation should use explicit states:

- `pending`: newly recorded and not eligible for retrieval.
- `approved`: reviewed against evidence and eligible for retrieval only within its authorised scope.
- `rejected`: not eligible for retrieval.
- `superseded`: replaced by a newer reviewed record; retained for audit, never retrieved as current guidance.

A review decision must be a one-way, atomic transition from `pending`. Concurrent reviewers must produce exactly one winning decision. A second or stale decision must return a conflict and must not overwrite the winner.

Corrections must create a new lesson linked to the prior lesson. They must not rewrite the original evidence or erase its review history. Reversal of an approval must be a separately audited withdrawal/supersession event.

## Evidence and provenance requirements

Before approval, the reviewer interface and server must make available:

1. The originating task and its persisted outcome/evaluation.
2. The lesson summary, type, source and bounded evidence payload.
3. Provenance identifying whether evidence came from deterministic evaluation, execution diagnostics, a source document or a human submission.
4. A stable content digest for the reviewed lesson and evidence, so a later content change cannot inherit an earlier approval.
5. Any source-document references and their trust/review state.
6. A clear warning that retrieved content is untrusted data, never instructions or policy.

Reject malformed, oversized, cyclic, non-finite or otherwise non-JSON evidence. Do not include secrets, raw exception messages, credentials or unnecessary personal data in reusable lessons.

## Reviewer authority and tenancy

Promotion must remain disabled until all of the following are implemented and tested:

- Verified user identity from a trusted authentication provider; never infer identity from a request-body field.
- Server-side role/permission checks for the specific organisation and memory scope.
- Tenant-scoped access to the originating task, lesson, evidence and review history.
- Separation of lesson author and reviewer where policy requires it.
- A server-derived reviewer principal and organisation ID recorded on every decision.
- Least-privilege API access, rate limiting and audit logging.

A shared API key plus caller-supplied `approved_by`, `reviewer` or `actor` values does not satisfy these requirements.

## Durable audit record

Each review event should be append-only and contain:

- Event ID and lesson ID.
- Previous state and resulting state.
- Decision and bounded reason.
- Reviewed content/evidence digest.
- Verified reviewer principal, role and organisation scope.
- Server timestamp and request/correlation ID.
- Relevant source/provenance references.

The lesson's current state may be stored for efficient retrieval, but it must be transactionally consistent with the immutable event. The audit record must not store credentials or full authentication tokens.

## Acceptance tests before enabling promotion

- Unauthenticated and invalid-role requests cannot review or promote lessons.
- A reviewer cannot access another tenant's lesson, task, evidence or review history.
- A lesson cannot be approved if its content/evidence digest differs from the reviewed version.
- Two concurrent reviewers yield one decision; the losing request receives a conflict.
- Rejected, pending and superseded lessons never appear in validated-memory retrieval.
- Approval, rejection, withdrawal and supersession each create durable audit events.
- A failed transaction leaves neither a partial state transition nor a missing audit event.
- Restart and migration tests preserve state and review history.
- Prompt-injection text in lesson evidence is treated as data and cannot alter policy or trigger actions.
- Retention, correction, export and deletion behaviour is defined for the applicable organisation and data-protection requirements.

## Release gate

Until the identity, authorisation, tenant isolation, immutable audit and acceptance-test requirements above are satisfied, lesson promotion must remain unavailable. Existing validated lessons, if any, must not be assumed to have verified reviewer identity merely because a legacy record contains a reviewer label.

This review gate is separate from approval to merge, deploy or change production. Those actions always require their own explicit release approval.
