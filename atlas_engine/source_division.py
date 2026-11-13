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
from urllib.parse import urlparse

from . import storage

MAX_DOCUMENT_CHARS = 1_000_000
TRUST_LEVELS = {"unverified", "reviewed", "authoritative"}
ALLOWED_SOURCE_URI_SCHEMES = {"http", "https", "git+https"}


def _validate_source_uri(uri: str) -> None:
    """Require an absolute web/repository URI without embedded credentials."""
    if not isinstance(uri, str) or not uri.strip():
        raise ValueError("Document source URI is required.")
    parsed = urlparse(uri.strip())
    if (
        parsed.scheme not in ALLOWED_SOURCE_URI_SCHEMES
        or not parsed.hostname
        or any(character.isspace() for character in parsed.hostname)
    ):
        raise ValueError("Source URI must be an absolute HTTP(S) or git+https URL with a valid host.")
    try:
        parsed.port  # Accessing this property validates the port syntax and range.
    except ValueError as exc:
        raise ValueError("Source URI contains an invalid port.") from exc
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Credentials must not be embedded in source URIs.")
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

    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("Document metadata must be an object.")
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
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Document title is required.")
    _validate_source_uri(uri)
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


def _frontmatter_value(frontmatter: str, key: str, allow_indented: bool = False) -> str | None:
    """Read a simple YAML scalar without adding a YAML dependency."""
    prefix = r"^\s*" if allow_indented else r"^"
    match = re.search(rf"{prefix}{re.escape(key)}:\s*(.+)$", frontmatter, re.MULTILINE)
    return match.group(1).strip().strip('"').strip("'") if match else None


def _bundled_document_metadata(path: Path) -> dict[str, str] | None:
    """Accept only Markdown notes carrying the explicit curated-reference marker."""
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        return None
    closing = content.find("\n---", 4)
    if closing < 0:
        return None
    frontmatter = content[4:closing]
    if _frontmatter_value(frontmatter, "review_status") != "curated-reference":
        return None
    document_id = _frontmatter_value(frontmatter, "id")
    title = _frontmatter_value(frontmatter, "title")
    division = _frontmatter_value(frontmatter, "division")
    publisher_match = re.search(r"^\s{2}publisher:\s*(.+)$", frontmatter, re.MULTILINE)
    retrieved = _frontmatter_value(frontmatter, "retrieved", allow_indented=True)
    url_match = re.search(
        r"^\s*(?:-\s*)?url:\s*[\"']?(https?://[^\"'\s]+)",
        frontmatter,
        re.MULTILINE,
    )
    if not all((document_id, title, division, publisher_match, url_match)):
        return None
    parsed_uri = urlparse(url_match.group(1))
    if parsed_uri.scheme not in {"http", "https"} or not parsed_uri.netloc:
        return None
    if len(content) > MAX_DOCUMENT_CHARS:
        return None
    return {
        "id": document_id,
        "title": title,
        "division": division,
        "publisher": publisher_match.group(1).strip().strip('"').strip("'"),
        "uri": url_match.group(1).strip().strip('"').strip("'"),
        "retrieved": retrieved or "unknown",
        "content": content.strip(),
    }


def load_bundled_knowledge() -> int:
    """Import explicitly curated Markdown notes from every library collection."""
    library_root = Path(__file__).resolve().parent.parent / "knowledge_library"
    imported = 0
    for path in sorted(library_root.rglob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        item = _bundled_document_metadata(path)
        if item is None:
            continue
        source_id = "bundled-" + re.sub(r"[^a-z0-9]+", "-", item["publisher"].lower()).strip("-")
        if storage.get_source(source_id) is None:
            register_source(
                source_id, item["publisher"], "curated_markdown_library",
                metadata={"collection": item["division"], "origin": "repository_bundle"},
            )
        relative_path = path.relative_to(library_root.parent).as_posix()
        normalized = item["content"]
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if storage.get_source_document_by_hash(source_id, digest) is not None:
            continue
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


_RETRIEVAL_STOP_WORDS = {
    "about", "after", "again", "against", "also", "among", "because", "been",
    "before", "being", "between", "both", "could", "does", "each", "from",
    "have", "into", "more", "most", "other", "over", "same", "some", "such",
    "than", "that", "their", "them", "then", "there", "these", "they", "this",
    "those", "through", "under", "very", "what", "when", "where", "which",
    "while", "with", "would", "your",
}


def _tokens(value: str) -> list[str]:
    """Normalize searchable text into stable lowercase word tokens."""
    return [
        token for token in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]{1,}", value.lower())
        if token not in _RETRIEVAL_STOP_WORDS
    ]


def _make_snippet(content: str, terms: set[str], width: int = 320) -> str:
    """Return a compact, plain-text excerpt around the earliest matched term."""
    normalized = re.sub(r"\s+", " ", content).strip()
    lowered = normalized.lower()
    positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
    if not positions:
        return normalized[:width] + ("…" if len(normalized) > width else "")
    start = max(0, min(positions) - width // 4)
    end = min(len(normalized), start + width)
    if start:
        start = normalized.find(" ", start)
        start = max(0, start + 1)
    if end < len(normalized):
        end = normalized.rfind(" ", start, end)
        if end <= start:
            end = min(len(normalized), start + width)
    excerpt = normalized[start:end].strip()
    return ("…" if start else "") + excerpt + ("…" if end < len(normalized) else "")


def retrieve(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Rank approved evidence with a lightweight BM25-style lexical scorer.

    The score is a relevance signal, not a truth or authority score. Search
    excludes pending/rejected material and returns provenance, matched terms,
    a short excerpt and a stable citation object for every result.
    """
    if not isinstance(query, str) or not query.strip():
        return []
    if not isinstance(limit, int) or limit < 1 or limit > 50:
        raise ValueError("Limit must be between 1 and 50.")
    query_tokens = _tokens(query)
    terms = set(query_tokens)
    if not terms:
        return []

    # The store currently exposes a bounded 500-record read; do not imply that
    # this lexical prototype searches an unbounded library.
    rows = storage.list_source_documents(approved_only=True, limit=500)
    if not rows:
        return []

    tokenized: list[tuple[dict[str, Any], list[str], list[str]]] = []
    document_frequency: dict[str, int] = {term: 0 for term in terms}
    total_length = 0
    for row in rows:
        title_tokens = _tokens(row["title"])
        content_tokens = _tokens(row["content"])
        all_tokens = title_tokens + content_tokens
        tokenized.append((row, title_tokens, all_tokens))
        total_length += len(all_tokens)
        present = set(all_tokens)
        for term in terms & present:
            document_frequency[term] += 1

    document_count = len(tokenized)
    average_length = max(1.0, total_length / document_count)
    ranked: list[tuple[float, str, dict[str, Any], set[str]]] = []
    k1 = 1.2
    b = 0.75
    for row, title_tokens, all_tokens in tokenized:
        frequencies: dict[str, int] = {}
        for token in all_tokens:
            if token in terms:
                frequencies[token] = frequencies.get(token, 0) + 1
        matched = set(frequencies)
        if not matched:
            continue
        length = max(1, len(all_tokens))
        score = 0.0
        for term, frequency in frequencies.items():
            df = document_frequency[term]
            inverse_document_frequency = max(
                0.0, __import__("math").log(1.0 + (document_count - df + 0.5) / (df + 0.5))
            )
            denominator = frequency + k1 * (1.0 - b + b * length / average_length)
            score += inverse_document_frequency * (frequency * (k1 + 1.0) / denominator)
            if term in title_tokens:
                score += inverse_document_frequency * 1.5
        if query_tokens and " ".join(query_tokens) in " ".join(all_tokens):
            score += 1.0
        if row["trust_level"] == "authoritative":
            score *= 1.05
        elif row["trust_level"] == "reviewed":
            score *= 1.0
        ranked.append((score, row["updated_at"], row, matched))

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    results: list[dict[str, Any]] = []
    for score, _updated, row, matched in ranked[:limit]:
        results.append({
            "id": row["id"],
            "source_id": row["source_id"],
            "title": row["title"],
            "uri": row["uri"],
            "content": row["content"],
            "trust_level": row["trust_level"],
            "content_sha256": row["content_sha256"],
            "score": round(score, 6),
            "matched_terms": sorted(matched),
            "snippet": _make_snippet(row["content"], matched),
            "citation": {
                "document_id": row["id"],
                "source_id": row["source_id"],
                "title": row["title"],
                "url": row["uri"],
                "content_sha256": row["content_sha256"],
                "trust_level": row["trust_level"],
            },
        })
    return results
