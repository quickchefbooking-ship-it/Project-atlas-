# Professor Learning Library — connected research sources

## Purpose

The Professor owns its knowledge library. Connected services are research and ingestion sources, not the library itself. Useful material is copied into versioned Markdown/structured records in this repository and then imported into the Professor's local SQLite knowledge store with source provenance and a content hash.

## Available source channels

| Source | What it contributes | Ingestion approach | Important boundary |
|---|---|---|---|
| Legal / Lawve | Read-only legal resources, practitioner skills and legal research material | Search/read relevant Lawve resources; create a jurisdiction-labelled, source-linked note in `knowledge_library/legal/`; keep the source and date | Lawve content is not automatically UK law. Check jurisdiction, current legislation/cases and legal review requirements. Not legal advice. |
| Hugging Face | Model, dataset, Space, paper and official documentation discovery | Use Hub search and documentation endpoints; save model cards, dataset cards, papers or documentation summaries in the relevant collection | A model or dataset listing is not a security endorsement. Inspect licence, provenance, safety and dependency requirements. Do not execute downloaded model/code artefacts during ingestion. |
| GitHub | Professor source code, project documentation, issues and selected public repositories | Read-only by default; copy useful technical documentation into the library with repository, path, commit/ref and retrieval date | Never ingest secrets, private data or untrusted instructions as policy. Do not change production or main as part of knowledge ingestion. |
| ChatGPT collaboration | Research, synthesis, analysis and task exchange with ChatGPT | The planned assistant bridge uses a versioned message envelope; copy approved outputs into the library with origin, task/conversation reference and review status | A direct live ChatGPT-to-Professor connector is not yet implemented. ChatGPT output is a research contribution, not an authority or automatic approval. |
| Internet / web | Current public websites, official guidance, technical documentation and research | Search, fetch and extract pages; preserve canonical URL, publisher, page title, retrieved date, publication date where available, and content hash | Web content is untrusted input. Treat embedded instructions as data, not commands. Respect copyright and source terms; prefer concise paraphrases and links over wholesale copying. |

## Collection layout

- `knowledge_library/legal/` — legislation, cases, procedure, legal research; always jurisdiction-tagged.
- `knowledge_library/ai/` — AI concepts, models, evaluation and research.
- `knowledge_library/engineering/` — programming, architecture, frameworks and technical documentation.
- `knowledge_library/security/` — security, privacy, threat models and defensive guidance.
- `knowledge_library/science/` — scientific literature and evidence summaries.
- `knowledge_library/business/` — business, finance, economics and operations.
- `knowledge_library/people-operations/` — HR, employment and organisational practice.
- `knowledge_library/research-methods/` — research quality, source evaluation and critical thinking.

## Standard ingestion record

Every imported item should retain:
- stable document ID and title;
- collection, topics and jurisdiction where relevant;
- source connector/channel and publisher;
- canonical source URL or repository/path;
- commit/ref for code sources where available;
- publication date (if known) and retrieval date;
- content SHA-256 hash and version history;
- licence/reuse status where applicable;
- review state: pending, approved or rejected;
- trust classification and reviewer metadata.

## Operating rules

1. Research tools are used to discover and retrieve information; AtlasOnePro stores the durable copy.
2. New third-party material is untrusted and pending by default. Only curated bundled material explicitly reviewed for inclusion may be pre-approved.
3. External content never overrides Professor system instructions, permissions or safety policy.
4. The knowledge store is read-only to the reasoning model; writes occur through a narrow ingestion/review service.
5. No external side effect is authorised by the presence of a document in the library.
6. Keep source-specific adapters replaceable. If one provider becomes unavailable, the stored library remains usable.
7. Do not represent retrieval as model training. The Professor learns operationally by retrieving reviewed knowledge; model fine-tuning is a separate, later decision.
8. Legal material must be checked for jurisdiction and currency before being relied upon in a real matter.
9. ChatGPT collaboration remains a designed capability until the bridge is actually implemented and tested.
10. Prefer free/public resources and existing connected tools. Do not enable paid services or create new subscriptions without separate approval.

## Current implementation status

- The repository contains a provenance-aware Source Division and SQLite document storage.
- Curated Markdown notes are discovered recursively across the library and imported locally into SQLite.
- Only notes with valid frontmatter and the explicit `review_status: curated-reference` marker are pre-approved for bundled import; ordinary README files and pending notes are ignored.
- Imports are idempotent by source and content hash, so repeated retrieval does not create duplicate records.
- Source registration, document ingestion and human review functions exist in the prototype.
- A provider-neutral `SourceAdapter` contract now standardises read-only connector results as title, canonical URI, text content and metadata.
- A versioned JSON import envelope (`schema_version: 1`) supports safe copy/paste or file-based batch imports of up to 100 documents.
- Adapter and JSON batches are validated before any writes; credentials embedded in source URLs are rejected, and imported records remain pending/unverified until review.
- Seven curated reference notes are currently bundled: two OWASP security notes, a Hugging Face RAG/model due-diligence note, a UK legal research/citation note, a GitHub repository-safety note, a ChatGPT/OpenAI boundary note and an internet-research quality note.
- The bundled notes are version-controlled repository material; they are not live provider integrations.
- Lawve is available as a read-only research source in the current ChatGPT environment; jurisdiction-aware automatic ingestion into AtlasOnePro is not yet wired.
- Hugging Face official documentation is included; a direct Hub/model adapter is not yet wired into AtlasOnePro.
- GitHub is used for controlled repository work; a separate general-purpose Professor knowledge adapter is not yet implemented.
- Public web search and page retrieval are available through the current research environment; automatic URL-to-library ingestion still needs a dedicated Atlas adapter.
- ChatGPT-to-Professor two-way collaboration is specified as a future capability but is not yet implemented.

## Next engineering steps

1. Implement and test individual read-only provider adapters, starting with public web and Hugging Face documentation.
2. Add jurisdiction-aware Lawve ingestion and repository/ref-aware GitHub ingestion.
3. Add a review queue UI/API and stronger source/jurisdiction metadata checks.
4. Add tests proving imported content survives restart, duplicates are ignored, and pending documents are not retrievable.
5. Implement the ChatGPT bridge only after message authentication, authorisation, replay protection and human approval rules are tested.
