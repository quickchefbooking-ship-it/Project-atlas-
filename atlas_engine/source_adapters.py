"""Provider-neutral adapter contract for feeding the Professor's knowledge library.

Adapters retrieve source material; this module validates and stages it. It does
not make network requests, store credentials, execute content, or auto-approve
documents. Provider implementations belong in separate, optional modules.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol
from urllib.parse import urlparse

from . import storage
from .source_division import MAX_DOCUMENT_CHARS, _encode_metadata, ingest_document

MAX_BATCH_DOCUMENTS = 100
MAX_BATCH_JSON_CHARS = 5_000_000
ALLOWED_URI_SCHEMES = {"http", "https", "git+https"}


@dataclass(frozen=True)
class SourceDocument:
    """One retrieved item in the provider-neutral ingestion format."""

    title: str
    uri: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class SourceAdapter(Protocol):
    """Contract implemented by a read-only research connector."""

    source_id: str

    def search(self, query: str, limit: int = 10) -> Iterable[SourceDocument]:
        """Return source documents; implementations must not perform writes."""


def _validate_document(document: SourceDocument) -> None:
    if not isinstance(document, SourceDocument):
        raise TypeError("Adapter results must be SourceDocument instances.")
    if not isinstance(document.title, str) or not document.title.strip():
        raise ValueError("Each source document requires a text title.")
    if not isinstance(document.uri, str) or not document.uri.strip():
        raise ValueError("Each source document requires a text URI.")
    parsed = urlparse(document.uri)
    if parsed.scheme not in ALLOWED_URI_SCHEMES or not parsed.netloc:
        raise ValueError("Source URI must be an absolute HTTP(S) or git+https URL.")
    if parsed.username or parsed.password:
        raise ValueError("Credentials must not be embedded in source URIs.")
    if not isinstance(document.content, str) or not document.content.strip():
        raise ValueError("Source document content must be non-empty text.")
    if len(document.content) > MAX_DOCUMENT_CHARS:
        raise ValueError("Source document exceeds the maximum permitted size.")
    if not isinstance(document.metadata, dict):
        raise ValueError("Source document metadata must be an object.")
    _encode_metadata(document.metadata)


def stage_adapter_results(
    adapter: SourceAdapter, query: str, limit: int = 10
) -> list[dict[str, Any]]:
    """Fetch a bounded batch and stage every item as pending/unverified."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("A non-empty research query is required.")
    if not isinstance(limit, int) or limit < 1 or limit > MAX_BATCH_DOCUMENTS:
        raise ValueError(f"Limit must be between 1 and {MAX_BATCH_DOCUMENTS}.")
    source_id = getattr(adapter, "source_id", None)
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("Adapter must declare a registered source_id.")
    if storage.get_source(source_id) is None:
        raise ValueError("Adapter source is not registered.")
    documents: list[SourceDocument] = []
    for index, document in enumerate(adapter.search(query, limit=limit)):
        if index >= limit:
            raise ValueError("Adapter returned more documents than the requested limit.")
        _validate_document(document)
        documents.append(document)
    staged: list[dict[str, Any]] = []
    for document in documents:
        staged.append(
            ingest_document(
                source_id,
                document.title,
                document.uri,
                document.content,
                metadata=document.metadata,
            )
        )
    return staged


def import_json_batch(source_id: str, payload: str) -> list[dict[str, Any]]:
    """Import a JSON envelope: {schema_version: 1, documents: [...]}.

    This is a file/paste import boundary, not a provider connection. Every
    imported record remains pending until explicitly reviewed.
    """
    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("JSON payload is required.")
    if len(payload) > MAX_BATCH_JSON_CHARS:
        raise ValueError("JSON batch exceeds the maximum permitted size.")
    if storage.get_source(source_id) is None:
        raise ValueError("Import source is not registered.")
    try:
        envelope = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Payload must be valid JSON.") from exc
    if not isinstance(envelope, dict) or envelope.get("schema_version") != 1:
        raise ValueError("Unsupported import envelope; expected schema_version 1.")
    documents = envelope.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ValueError("Envelope must contain a non-empty documents array.")
    if len(documents) > MAX_BATCH_DOCUMENTS:
        raise ValueError(f"Batch may contain at most {MAX_BATCH_DOCUMENTS} documents.")

    validated: list[SourceDocument] = []
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("Each document entry must be an object.")
        allowed = {"title", "uri", "content", "metadata"}
        if set(document) - allowed or not {"title", "uri", "content"} <= set(document):
            raise ValueError("Document fields must be title, uri, content and optional metadata.")
        item = SourceDocument(
            title=document["title"],
            uri=document["uri"],
            content=document["content"],
            metadata=document.get("metadata", {}),
        )
        _validate_document(item)
        validated.append(item)

    staged: list[dict[str, Any]] = []
    for item in validated:
        staged.append(
            ingest_document(
                source_id, item.title, item.uri, item.content, metadata=item.metadata
            )
        )
    return staged
