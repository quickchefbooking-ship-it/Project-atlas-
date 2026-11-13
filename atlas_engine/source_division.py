"""Source Division: provenance-aware, approval-gated knowledge storage.

External connectors must implement a narrow adapter and explicitly register a source.
This module does not fetch URLs, execute imported content, or grant connector access.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from . import storage

MAX_DOCUMENT_CHARS = 1_000_000
TRUST_LEVELS = {"unverified", "reviewed", "authoritative"}
DOCUMENT_STATES = {"pending", "approved", "rejected"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_source(
    source_id: str,
    name: str,
    source_type: str,
    access_mode: str = "read_only",
    enabled: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Register a source descriptor; enabled never means credentials are available."""
    if not source_id.strip() or not name.strip() or not source_type.strip():
        raise ValueError("Source ID, name and type are required.")
    if access_mode not in {"read_only", "draft_only", "approval_gated"}:
        raise ValueError("Unsupported source access mode.")
    record = {
        "id": source_id,
        "name": name,
        "source_type": source_type,
        "access_mode": access_mode,
        "enabled": bool(enabled),
        "metadata_json": json.dumps(metadata or {}, sort_keys=True),
        "created_at": _now(),
        "updated_at": _now(),
    }
    storage.save_source(record)
    return record


def list_sources() -> list[dict[str, Any]]:
    return storage.list_sources()


def ingest_document(
    source_id: str,
    title: str,
    uri: str,
    content: str,
    trust_level: str = "unverified",
    state: str = "pending",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Store bounded source material with provenance; new records default to pending."""
    if trust_level not in TRUST_LEVELS:
        raise ValueError("Unsupported trust level.")
    if state not in DOCUMENT_STATES:
        raise ValueError("Unsupported document state.")
    if not title.strip() or not uri.strip():
        raise ValueError("Document title and source URI are required.")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Document content is required.")
    if len(content) > MAX_DOCUMENT_CHARS:
        raise ValueError("Document exceeds the maximum permitted size.")
    if storage.get_source(source_id) is None:
        raise ValueError("Source is not registered.")
    normalized = content.strip()
    return storage.save_source_document({
        "id": f"source-doc-{uuid4().hex}",
        "source_id": source_id,
        "title": title.strip(),
        "uri": uri.strip(),
        "content": normalized,
        "content_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "trust_level": trust_level,
        "state": state,
        "metadata_json": json.dumps(metadata or {}, sort_keys=True),
        "created_at": _now(),
        "updated_at": _now(),
    })


def review_document(document_id: str, decision: str, reviewer: str) -> dict[str, Any]:
    """Record a review decision; reviewer is audit metadata, not verified identity."""
    if decision not in {"approved", "rejected"}:
        raise ValueError("Decision must be approved or rejected.")
    if not reviewer.strip():
        raise ValueError("Reviewer is required.")
    if not storage.review_source_document(document_id, decision, reviewer.strip(), _now()):
        raise ValueError("Source document not found.")
    return storage.get_source_document(document_id)


def retrieve(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Keyword retrieval over approved material only; return provenance with every hit."""
    if not isinstance(query, str) or not query.strip():
        return []
    if not isinstance(limit, int) or limit < 1 or limit > 50:
        raise ValueError("Limit must be between 1 and 50.")
    terms = {term.lower() for term in re.findall(r"[a-zA-Z0-9_]+", query) if len(term) > 2}
    if not terms:
        return []
    rows = storage.list_source_documents(approved_only=True, limit=500)
    ranked: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        text = f"{row['title']} {row['content']}".lower()
        score = sum(text.count(term) for term in terms)
        if score:
            ranked.append((score, row))
    ranked.sort(key=lambda item: (item[0], item[1]["updated_at"]), reverse=True)
    return [
        {
            "id": row["id"],
            "source_id": row["source_id"],
            "title": row["title"],
            "uri": row["uri"],
            "content": row["content"],
            "trust_level": row["trust_level"],
            "content_sha256": row["content_sha256"],
            "score": score,
        }
        for score, row in ranked[:limit]
    ]
