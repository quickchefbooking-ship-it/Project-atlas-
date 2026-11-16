# Professor evidence excerpt traceability

**Status: deterministic traceability primitive implemented in a draft branch; not a complete source-verification or truth-assessment system.**

## Purpose

Research conclusions must not treat a reviewer-supplied `supports` or `challenges` label as independently verified fact. The traceability primitive binds a quoted excerpt to a specific source-text snapshot and records who reviewed the annotation, if reviewer attribution is supplied.

Implementation: `atlas_engine/evidence_traceability.py`, tested by `tests/test_evidence_traceability.py`.

## What it verifies

Given a source URI, source text snapshot, excerpt, locator, claim and reviewer relation, it:
1. Requires an absolute HTTPS source URI without embedded credentials or alternate ports.
2. Bounds source text to 1,000,000 characters and excerpt to 2,000 characters.
3. Computes SHA-256 digests for the full supplied source snapshot and the excerpt.
4. Checks whether the exact excerpt is a substring of that source snapshot.
5. Optionally compares the snapshot digest with an expected digest to detect changed source content.
6. Requires reviewer ID and timezone-aware ISO-8601 review timestamp together, or records the item as unreviewed.
7. Preserves the claim ID/text, reviewer-supplied relation, locator and explicit non-assessment fields.

Traceability states:
- `exact_excerpt_found`: the exact excerpt occurs in the supplied snapshot and any expected digest matches.
- `excerpt_not_found`: the excerpt is not present in the supplied snapshot.
- `source_version_mismatch`: an expected digest was supplied and does not match the current snapshot.

## What it does not verify

- It does not prove the excerpt supports or challenges the claim.
- The standalone traceability helper does not independently resolve a locator to a PDF page, paragraph, table or section.
- A reviewer ID passed directly to the standalone helper is attributed data, not authenticated identity. The existing authenticated tenant evidence-review HTTP route separately derives reviewer attribution from the verified principal and rejects client-supplied reviewer IDs.
- It does not assess publisher/source credibility, peer review, methods, sample size, bias, causality, recency or conflicts of interest.
- It does not establish independent corroboration. Two URLs or excerpts may refer to the same underlying study.
- It does not automatically fetch or preserve a canonical provider snapshot. The caller must supply the source text obtained through an approved source adapter.
- It does not make an excerpt safe to treat as an instruction; source content remains untrusted reference data.

The output therefore labels claim support, source credibility and independence as `not_assessed` or `not_machine_assessed`. Exact text matching is a provenance check, not a truth check.

## Approved-source binding — draft implementation

A follow-on draft adds `atlas_engine/approved_source_traceability.py`. Its public function accepts a persisted source-document ID and excerpt annotation fields; it resolves the source text, URI and digest from Atlas storage rather than accepting them from the caller. It requires the stored document to be `approved` with `reviewed` or `authoritative` trust level, recomputes the content digest, and passes the stored digest as the expected source version. The result includes the source document ID, title, state, trust level, digest and the source-ingestion reviewer label. That reviewer label is explicitly not treated as verified identity.

The same draft adds SQLite triggers that prevent source snapshot content/provenance fields from being updated and prevent source-document deletion. Review-state transitions remain handled through the existing pending-to-approved/rejected path. This is database-level immutability within the configured SQLite database, not tamper-proof storage against an administrator who can replace the database file or drop triggers.

Tests cover approved-only lookup, pending/rejected rejection, missing IDs, digest linkage, caller attempts to inject source text/URI, and snapshot update/delete prevention. The work remains a draft and is not yet integrated into the authenticated Professor research/report route.


## Verified reviewer attribution — existing authenticated workflow

The existing `POST /professor/tenant/plans/{plan_id}/evidence/{bundle_step_id}/review` route requires `require_verified_principal` and the `evidence:review` scope. It derives a stable pseudonymous reviewer ID from the verified issuer and subject; the request schema forbids extra fields, including a caller-supplied reviewer ID. Review records are tenant-scoped and append-only. A regression test now checks the exact digest-derived attribution rather than only checking its prefix.

A follow-on draft adds stable annotation IDs and explicit `active`/`superseded` states. A correction must identify an existing annotation on the same claim and source and provide a reason; the prior annotation is retained with a supersession pointer, and the replacement is separately attributed. Each review revision links to the preceding revision with `supersedes_review_id`, `revision_kind` and a bounded reason. Earlier revision snapshots remain immutable. Evaluation excludes superseded annotations from the current classification while retaining a separate audit list, so a corrected label does not continue influencing the latest result.

This identity gate already existed before the current locator work. It authenticates the reviewer at the tenant review endpoint; it does not yet bind source-document ingestion review to that same principal or connect the approved-source traceability helper to the tenant evidence-review route.

## HTML locator resolution — draft implementation

`atlas_engine/evidence_locators.py` adds a deterministic resolver for approved stored HTML snapshots. It accepts only source documents marked `content_type: text/html`, requires approved/reviewed status, recomputes the immutable snapshot digest, and extracts semantic text blocks such as headings, paragraphs, list items, quotations and table cells. It returns structural paths, excerpt fingerprints and explicit statuses for a unique match, no match or ambiguous matches. Script, style, SVG, template and noscript content are excluded. It never fetches a URL or runs a browser.

The locator is relative to the stored HTML snapshot and may change in a later version. It does not resolve a live page, prove claim support, or authenticate the source publisher. The authenticated evidence-review route now attaches the traceability result to a reviewer annotation only when the exact bundle source URI matches and a unique excerpt block is found. PDF page-coordinate resolution remains outstanding; no PDF parser dependency has been added or selected.

## Tenant-owned source snapshot boundary — draft implementation

A further draft adds `atlas_engine/tenant_approved_sources.py` and initializes its schema in the separate tenant data database. It stages immutable source snapshots under a compound `(tenant_id, document_id)` key, records the staging principal, bounds source text and metadata, accepts only HTTPS source URIs, and keeps new records pending by default. Approval/rejection is a one-way pending-to-reviewed decision with server-derived reviewer attribution. Approved lookup always requires both the authenticated tenant ID and document ID; a document ID from another tenant returns no record. Snapshot content/provenance cannot be updated or deleted through normal SQLite operations.

The follow-on draft adds `atlas_engine/tenant_approved_sources_api.py` with authenticated `POST /professor/tenant/sources` staging and `POST /professor/tenant/sources/{document_id}/review` approval/rejection routes. Separate `evidence:source:write` and `evidence:source:approve` scopes are required. Both tenant ID and pseudonymous actor/reviewer ID are derived from the verified principal; request models reject extra fields, so clients cannot supply tenant or reviewer IDs. New sources remain pending until separately approved. Metadata is capped at 16 KiB, source text at 1,000,000 characters, and only HTTPS source URIs are accepted. Tests cover missing scopes, forged tenant/reviewer fields, cross-tenant review attempts and approved-only lookup. The tenant source route layer is integrated by the follow-on authenticated evidence-review change: an annotation may include both `source_document_id` and `excerpt`; the route resolves only through `get_approved_tenant_source_document` using the verified principal's tenant, then resolves a unique HTML semantic block. The source URI must exactly match the URI recorded for that source in the completed evidence bundle. Pending/rejected, cross-tenant, non-HTML, missing, ambiguous, or URI-mismatched sources fail closed. The legacy global source store remains separate and is never consulted by this tenant-linked path. SQLite triggers are integrity controls, not tamper-proof storage against an administrator with database-file access. PDF content may be staged as metadata, but no PDF extraction is implemented.

Tests cover pending-by-default, approval and rejection, reviewer spoofing/repeated decisions, cross-tenant lookup isolation, unsafe URI rejection, digest linkage, and snapshot immutability.

## Next verification gates

1. Add reviewer correction/supersession history and independently attributable source-approval review, while retaining append-only revisions.
2. Add PDF page/paragraph/table locator resolution after selecting and reviewing a maintained parser dependency and its security/supply-chain implications.
3. Bind source-ingestion approval and source-snapshot provenance to verified reviewer identity, and add reviewer correction/supersession history.
4. Add independent reviewer workflow, disagreement/correction/supersession history and tenant scoping.
5. Assess source type, publication status, retraction/correction state, study design, methodology and limitations with explicit evidence; do not collapse these into one opaque quality score.
6. Add duplicate-work detection across DOI, canonical URL and provider identifiers before counting corroboration.
7. Keep claims and source content labelled as untrusted data in Professor prompts and reports.

Until these gates pass, Professor must describe these results as traceability checks and reviewer annotations, not independent verification of factual truth.


## Source publication, methodology and retraction assessments — draft implementation

A further draft adds `atlas_engine/tenant_source_assessments.py` and the authenticated route `POST /professor/tenant/sources/{document_id}/assessments`. It records append-only, tenant-scoped assessment revisions for publication status (`published`, `preprint`, `unpublished`, `unknown`), retraction/correction status (`not_known`, `correction_notice`, `expression_of_concern`, `retracted`, `unknown`) and study-design category. Each assessment includes bounded HTTPS evidence references, a reviewer rationale, server-derived reviewer attribution and a timestamp. A dedicated `evidence:source:assess` scope is required. The source must already be approved and reviewed/authoritative within the same tenant. Caller-supplied tenant or reviewer IDs are rejected.

Assessments are append-only and multiple revisions are preserved. The system deliberately permits `unknown`; no notice found is not treated as proof of no retraction. It emits `quality_score: not_scored` and does not infer source quality, methodology adequacy or factual truth from the labels. The evidence references and rationale are reviewer-supplied and are not independently fetched or validated for the truth of the assessment. This is a structured human review record, not an automated source-quality engine or external retraction-monitoring service.
