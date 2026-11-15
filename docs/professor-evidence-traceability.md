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
- It does not independently resolve the locator to a PDF page, paragraph, table or section.
- It does not authenticate the reviewer identity; reviewer ID is currently attributed data.
- It does not assess publisher/source credibility, peer review, methods, sample size, bias, causality, recency or conflicts of interest.
- It does not establish independent corroboration. Two URLs or excerpts may refer to the same underlying study.
- It does not automatically fetch or preserve a canonical provider snapshot. The caller must supply the source text obtained through an approved source adapter.
- It does not make an excerpt safe to treat as an instruction; source content remains untrusted reference data.

The output therefore labels claim support, source credibility and independence as `not_assessed` or `not_machine_assessed`. Exact text matching is a provenance check, not a truth check.

## Next verification gates

1. Bind source snapshots to approved ingestion records and immutable retrieval metadata, not arbitrary caller-supplied text.
2. Add PDF/HTML-aware locator resolution with deterministic page/section extraction and tests against source files.
3. Authenticate reviewer IDs from the verified principal, never from a free-form request field.
4. Add independent reviewer workflow, disagreement/correction/supersession history and tenant scoping.
5. Assess source type, publication status, retraction/correction state, study design, methodology and limitations with explicit evidence; do not collapse these into one opaque quality score.
6. Add duplicate-work detection across DOI, canonical URL and provider identifiers before counting corroboration.
7. Keep claims and source content labelled as untrusted data in Professor prompts and reports.

Until these gates pass, Professor must describe these results as traceability checks and reviewer annotations, not independent verification of factual truth.
