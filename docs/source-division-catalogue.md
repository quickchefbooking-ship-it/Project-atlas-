# Source Division — resource catalogue

This is a discovery and integration backlog for the Professor's Source Division.

**Important:** a connector appearing in ChatGPT's available tool ecosystem does not mean AtlasOnePro has credentials or runtime access to it. Every entry below is a candidate adapter. The Professor must not claim a source is connected until its adapter is implemented, authenticated, scoped and tested inside AtlasOnePro.

## Candidate knowledge sources

| Resource family | Available resource/tool candidates | Intended use | Initial access |
| --- | --- | --- | --- |
| Public web and pages | Firecrawl search, scrape, map and crawl; official websites | Discover and extract public information with canonical URLs | Read-only |
| Scholarly research | Consensus, SciSpace, Firecrawl research index | Papers, abstracts, citations and open-access full text | Read-only |
| Developer knowledge | GitHub repositories, issues, pull requests and official docs; Firecrawl developer search | Source code, architecture, release notes and technical guidance | Read-only |
| Models and datasets | Hugging Face models, datasets, Spaces and documentation | Model cards, dataset descriptions, licenses and API docs | Read-only |
| Internal files | ChatGPT Files / Library and explicitly selected project documents | User-approved documents, plans and internal reference material | Read-only; explicit selection |
| Email and communications | Gmail and other separately authorised messaging integrations | Search and summarise approved messages; draft responses | Read-only / draft-only |
| Commerce and operations | Shopify and marketplace integrations | Product, order and operational reference data | Read-only |
| Payments | Stripe | Product, subscription and payment reference data | Read-only; no payment actions |
| Analytics and publishing | Metricool, vidIQ and marketing analytics integrations | Performance data, content research and reporting | Read-only / draft-only |
| Finance and markets | Trading and market-data integrations such as Alpaca and AlphaYou | Market research and portfolio context | Read-only; no orders or transfers |
| Jobs and procurement | Job search, tender and grant discovery integrations | Opportunity research and deadline tracking | Read-only |
| Atlas internal knowledge | Validated lessons, task history, approved plans and source documents | Reuse Atlas-owned evidence and decisions | Internal read |

## Integration order

1. **Local foundation:** source registry, normalized document format, content hashes, approval queue and provenance-aware retrieval.
2. **Public research:** web extraction, scholarly metadata and official technical documentation.
3. **Project knowledge:** selected GitHub repositories and explicitly selected project files.
4. **Business systems:** narrowly scoped read-only adapters, one connector at a time.
5. **Private communications:** only after identity, user consent, tenant isolation, retention and deletion controls are implemented.

## Source adapter acceptance checklist

Every adapter must document its owner, connection method, credential storage, delegated scopes, data classes, rate limits, retention, licensing, freshness, error handling and revocation process. It must return normalized documents with source ID, canonical URI, retrieval timestamp, content hash and provenance metadata. It must not write back to the source system.

## Not in scope for this arm

No credential harvesting, unrestricted crawling, access-control bypass, private account scraping, automatic email sending, social publishing, payments, trading, deletion or permission changes. Source Division supplies evidence to the Professor; it does not perform external actions.

## Prototype implementation notes

The current repository implementation is a local ingestion and retrieval foundation, not a live connector suite. It validates absolute HTTP(S) and git+https source references at the ingestion boundary, rejects embedded URL credentials and malformed hosts or ports, hashes normalized content, and deduplicates records by source and content hash. New imports remain pending and unverified. A successful approval changes the document state to approved and its trust classification to reviewed; rejected material remains excluded from retrieval. These controls do not authenticate the reviewer: reviewer names are audit metadata until identity and role-based authorization are implemented.

The bundled curated notes are imported idempotently at application startup. External web, GitHub, Hugging Face, Lawve, research and business-system adapters still need to be implemented and tested inside the AtlasOnePro runtime. Do not label any of those services as connected merely because they are available in the ChatGPT workspace.

## Authenticated API surface

The Professor exposes the Source Division through the FastAPI service. Every route below requires the configured `X-API-Key` header when API authentication is enabled:

- `GET /sources` — registered source catalogue (descriptors and safe metadata only).
- `GET /sources/documents?state=pending&limit=100` — bounded review queue. Supported states are `pending`, `approved`, and `rejected`. The list intentionally omits document bodies.
- `POST /sources/import` — paste/import a JSON envelope into a registered source. The API returns document IDs, hashes and pending status; it never approves an import.
- `GET /sources/search?q=...` — keyword search over approved documents only, with source URI and SHA-256 provenance on every result.

Example import body:

```json
{
  "source_id": "manual-research",
  "payload": {
    "schema_version": 1,
    "documents": [
      {
        "title": "Research note title",
        "uri": "https://example.org/research",
        "content": "The copied, source-backed text goes here.",
        "metadata": {
          "publisher": "Example publisher",
          "retrieved_at": "2026-11-13"
        }
      }
    ]
  }
}
```

The source ID must already exist in the catalogue. The payload is capped by the import adapter's document, batch and character limits and is validated as a complete batch before any writes occur. Duplicate source/content pairs return the existing record. The API deliberately has no document-approval route yet: the current reviewer field is audit metadata, not authenticated user identity or role-based authorization. Human review must therefore remain an explicitly controlled operator action until real identity and reviewer permissions are implemented. Do not expose a caller-supplied reviewer name as an approval credential.
