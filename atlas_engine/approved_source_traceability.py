"""Evidence excerpt traceability bound to approved, immutable source snapshots.

This module resolves source text by its persisted document ID. Callers cannot
supply or substitute source text, URI, digest, trust level or reviewer metadata.
"""
from __future__ import annotations

import hashlib
from typing import Any

from . import storage
from .evidence_traceability import verify_evidence_excerpt


def trace_approved_source_excerpt(
    *,
    source_document_id: str,
    excerpt: str,
    locator: str,
    claim_id: str,
    claim_text: str,
    relation: str,
) -> dict[str, Any]:
    """Verify an excerpt against an approved source document stored by Atlas."""
    if not isinstance(source_document_id, str) or not source_document_id.strip():
        raise ValueError("A source_document_id is required.")

    document = storage.get_source_document(source_document_id)
    if document is None:
        raise ValueError("Approved source document was not found.")
    if document.get("state") != "approved" or document.get("trust_level") not in {
        "reviewed", "authoritative",
    }:
        raise ValueError("Only an approved, reviewed source document can be traced.")

    source_text = document.get("content")
    stored_digest = document.get("content_sha256")
    if not isinstance(source_text, str) or not isinstance(stored_digest, str):
        raise ValueError("Stored source snapshot is incomplete.")
    actual_digest = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    if actual_digest != stored_digest:
        raise ValueError("Stored source snapshot digest does not match its content.")

    result = verify_evidence_excerpt(
        source_uri=document["uri"],
        source_text=source_text,
        excerpt=excerpt,
        locator=locator,
        claim_id=claim_id,
        claim_text=claim_text,
        relation=relation,
        expected_source_sha256=stored_digest,
    )
    result.update({
        "source_document_id": document["id"],
        "source_title": document["title"],
        "source_state": document["state"],
        "source_trust_level": document["trust_level"],
        "source_content_sha256": stored_digest,
        # This is the source-ingestion review label, not verified identity.
        "source_reviewed_by": document.get("reviewed_by"),
        "source_created_at": document["created_at"],
    })
    return result
