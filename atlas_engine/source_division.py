"""Source Division: provenance-aware, approval-gated knowledge storage.

External connectors must implement a narrow adapter and explicitly register a source.
This module does not fetch URLs, execute imported content, or grant connector access.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import storage

MAX_DOCUMENT_CHARS = 1_000_000
TRUST_LEVELS = {"unverified", "reviewed", "authoritative"}
DOCUMENT_STATES = {"pending", "approved", "rejected"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encode_metadata(metadata: dict[str, Any] | None) -> str:
    """Reject credential-like metadata keys before persistence."""
    forbidden = re.compile(r"(secret|token|password|api[_-]?key|authorization|cookie|credential)", re.I)

    def inspect(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if forbidden.search(str(key)):
                    raise ValueError("Credential-like metadata fields are not permitted.")
                inspect(nested)
        elif isinstance(value, list):
            for nested in value:
                inspect(nested)

    safe_metadata = metadata or {}
    inspect(safe_metadata)
    return json.dumps(safe_metadata, sort_keys=True)


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
        "metadata_json": _encode_metadata(metadata),
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
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Store bounded source material as unverified and pending review."""
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
        "trust_level": "unverified",
        "state": "pending",
        "metadata_json": _encode_metadata(metadata),
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


def _frontmatter_value(frontmatter: str, key: str) -> str | None:
    """Read a simple top-level YAML scalar without adding a YAML dependency."""
    match = re.search(rf"^{re.escape(key)}:\\s*[\\"']?([^\\n\\"']+)", frontmatter, re.MULTILINE)
    return match.group(1).strip() if match else None


def _bundled_document_metadata(path: Path) -> dict[str, str] | None:
    """Accept only Markdown notes carrying the explicit curated-reference marker."""
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\\n"):
        return None
    closing = content.find("\\n---", 4)
    if closing < 0:
        return None
    frontmatter = content[4:closing]
    if _frontmatter_value(frontmatter, "review_status") != "curated-reference":
        return None
    document_id = _frontmatter_value(frontmatter, "id")
    title = _frontmatter_value(frontmatter, "title")
    division = _frontmatter_value(frontmatter, "division")
    publisher_match = re.search(r"^  publisher:\\s*[\\"']?([^\\n\\"']+)", frontmatter, re.MULTILINE)
    retrieved_match = re.search(r"^  retrieved:\\s*[\\"']?([^\\n\\"']+)", frontmatter, re.MULTILINE)
    # The source may expose a single URL or a list of guidance URLs. Preserve
    # the first canonical source URI for indexing; the note retains all sources.
    url_match = re.search(r"^  url:\\s*[\\"']?(https?://[^\\s\\"']+)", frontmatter, re.MULTILINE)
    if not url_match:
        url_match = re.search(r"^\\s+- url:\\s*[\\"']?(https?://[^\\s\\"']+)", frontmatter, re.MULTILINE)
    if not all((document_id, title, division, publisher_match, url_match)):
        return None
    return {
        "id": document_id,
        "title": title,
        "division": division,
        "publisher": publisher_match.group(1).strip(),
        "uri": url_match.group(1).strip(),
        "retrieved": retrieved_match.group(1).strip() if retrieved_match else "unknown",
        "content": content.strip(),
    }


def load_bundled_knowledge() -> int:
    """Import explicitly curated Markdown notes from every library collection.

    Files without valid frontmatter and the exact curated-reference marker are
    ignored. New material is therefore not silently promoted merely because it
    was copied into the repository.
    """
    library_root = Path(__file__).resolve().parent.parent / "knowledge_library"
    candidates = sorted(library_root.rglob("*.md"))
    imported = 0
    for path in candidates:
        if path.name.lower() == "readme.md":
            continue
        item = _bundled_document_metadata(path)
        if item is None:
            continue
        source_id = "bundled-" + re.sub(r"[^a-z0-9]+", "-", item["publisher"].lower()).strip("-")
        register_source(
            source_id,
            item["publisher"],
            "curated_markdown_library",
            metadata={"collection": item["division"], "origin": "repository_bundle"},
        )
        relative_path = path.relative_to(library_root.parent).as_posix()
        normalized = item["content"]
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        storage.save_source_document({
            "id": f"bundle-{digest[:24]}",
            "source_id": source_id,
            "title": item["title"],
            "uri": item["uri"],
            "content": normalized,
            "content_sha256": digest,
            "trust_level": "reviewed",
            "state": "approved",
            "metadata_json": _encode_metadata({
                "bundle_path": relative_path,
                "document_id": item["id"],
                "collection": item["division"],
                "review_status": "curated_reference",
                "retrieved_at": item["retrieved"],
            }),
            "created_at": _now(),
            "updated_at": _now(),
        })
        imported += 1
    return imported


def retrieve(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Keyword retrieval over approved material only; return provenance with every hit."""
    load_bundled_knowledge()
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
