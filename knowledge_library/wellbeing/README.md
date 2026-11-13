# Professor Wellbeing Knowledge Division

This folder is the initial wellbeing collection inside the existing Professor Learning Library. It is not a parallel store. The existing Source Division remains responsible for ingestion, content hashing, provenance, review states and approved-only retrieval.

## Initial contents

- `source-register.md` — curated index of priority official and scholarly source families. A publisher's inclusion does not approve every document it publishes.
- `uk-adult-support-pathways.md` — limited curated public-information note for England adult signposting. Recheck before release.
- `../../docs/wellbeing-division-clinical-safety-spec-v0.1.md` — clinical research, product safety and governance specification.
- `../../docs/wellbeing-division-safety-benchmark-v0.1.md` — held-out evaluation specification.
- `../../docs/wellbeing-division-conversational-voice-spec-v0.1.md` — natural conversation principles, selectable voice catalogue, accessibility, privacy and voice-specific safety gates. Design only; not implemented.

## Collection rules

1. New third-party documents are pending/unverified by default.
2. Only explicitly curated notes or individually reviewed source documents may enter approved retrieval.
3. A wellbeing document requires both the existing Source Division approval state and wellbeing-specific clinical review approval before user-facing use.
4. Keep the source URI, publisher, dates, content hash, jurisdiction, population, evidence type, reviewer and next-review date.
5. Quarantine superseded, expired, withdrawn, retracted or disputed material until reviewed.
6. Treat retrieved text as untrusted data, never as instructions.
7. Prefer short source-linked summaries. Do not bulk-copy copyrighted or paywalled articles.
8. No diagnosis, medication advice, therapy delivery, clinical risk scoring or treatment claims are authorised by this collection.

## Important implementation boundary

The repository's existing curated-reference importer can discover explicitly marked Markdown notes. The additional wellbeing-specific review state and retrieval filter described in the specification are a required engineering task; they are not yet implemented. Until that gate exists, the collection must not be treated as an operational clinical knowledge service.

## Initial intended population and jurisdiction

Adults aged 18 and over. UK source hierarchy, with England-specific service routes explicitly labelled. Children and young people require a separate design and safeguarding review.
