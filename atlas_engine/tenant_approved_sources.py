"""Tenant-owned approved evidence snapshots.

This repository is deliberately separate from the legacy global source store.
Every lookup is tenant-qualified; a document identifier is never sufficient
authority to read another tenant's source material.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit


MAX_SOURCE_CHARS = 1_000_000
MAX_TITLE_CHARS = 500
_ALLOWED_TRUST = {"reviewed", "authoritative"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_source_uri(uri: str) -> str:
    if not isinstance(uri, str) or len(uri) > 2048:
        raise ValueError("Source URI must be an absolute HTTPS URL.")
    parsed = urlsplit(uri)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.port not in (None, 443)
            or parsed.fragment):
        raise ValueError("Source URI must be an absolute HTTPS URL without credentials, fragments or alternate ports.")
    return uri


def initialize_tenant_approved_source_schema(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS tenant_approved_source_documents (
      tenant_id TEXT NOT NULL,
      document_id TEXT NOT NULL,
      title TEXT NOT NULL,
      uri TEXT NOT NULL,
      content TEXT NOT NULL,
      content_sha256 TEXT NOT NULL,
      content_type TEXT NOT NULL,
      trust_level TEXT NOT NULL CHECK(trust_level IN ('unverified','reviewed','authoritative')),
      state TEXT NOT NULL CHECK(state IN ('pending','approved','rejected')),
      staged_by TEXT NOT NULL,
      reviewed_by TEXT,
      created_at TEXT NOT NULL,
      reviewed_at TEXT,
      metadata_json TEXT NOT NULL DEFAULT '{}',
      PRIMARY KEY(tenant_id, document_id)
    );
    CREATE INDEX IF NOT EXISTS idx_tenant_source_documents_state
      ON tenant_approved_source_documents(tenant_id, state, created_at DESC);
    CREATE TRIGGER IF NOT EXISTS tenant_source_snapshot_no_update
      BEFORE UPDATE OF title, uri, content, content_sha256, content_type,
                       staged_by, created_at, metadata_json
      ON tenant_approved_source_documents BEGIN
      SELECT RAISE(ABORT, 'tenant source snapshot is immutable');
    END;
    CREATE TRIGGER IF NOT EXISTS tenant_source_no_delete
      BEFORE DELETE ON tenant_approved_source_documents BEGIN
      SELECT RAISE(ABORT, 'tenant source snapshots cannot be deleted');
    END;
    CREATE TRIGGER IF NOT EXISTS tenant_source_state_transition
      BEFORE UPDATE OF state, trust_level, reviewed_by, reviewed_at
      ON tenant_approved_source_documents
      WHEN NOT (
        OLD.state = 'pending'
        AND NEW.state IN ('approved','rejected')
        AND NEW.reviewed_by IS NOT NULL
        AND NEW.reviewed_at IS NOT NULL
        AND NEW.trust_level IN ('unverified','reviewed','authoritative')
      )
      BEGIN
        SELECT RAISE(ABORT, 'invalid tenant source review transition');
      END;
    """)


def stage_tenant_source_document(
    db: sqlite3.Connection, *, tenant_id: str, staged_by: str,
    title: str, uri: str, content: str, content_type: str = "text/html",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a pending immutable source snapshot inside the tenant database."""
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("A tenant identity is required.")
    if not isinstance(staged_by, str) or not staged_by.strip():
        raise ValueError("A verified staging identity is required.")
    if not isinstance(title, str) or not title.strip() or len(title) > MAX_TITLE_CHARS:
        raise ValueError("Source title must contain 1 to 500 characters.")
    _validate_source_uri(uri)
    if not isinstance(content, str) or not content.strip() or len(content) > MAX_SOURCE_CHARS:
        raise ValueError("Source content must contain 1 to 1,000,000 characters.")
    if content_type not in {"text/html", "text/plain", "application/pdf"}:
        raise ValueError("Unsupported source content type.")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("Source metadata must be an object.")
    encoded_metadata = json.dumps(metadata or {}, ensure_ascii=False, allow_nan=False,
                                  sort_keys=True, separators=(",", ":"))
    document_id = "tsrc_" + uuid.uuid4().hex
    created_at = _now()
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    db.execute("""
      INSERT INTO tenant_approved_source_documents
        (tenant_id,document_id,title,uri,content,content_sha256,content_type,
         trust_level,state,staged_by,created_at,metadata_json)
      VALUES(?,?,?,?,?,?,?,'unverified','pending',?,?,?)
    """, (tenant_id, document_id, title.strip(), uri, content, digest,
          content_type, staged_by, created_at, encoded_metadata))
    return {
        "document_id": document_id, "title": title.strip(), "uri": uri,
        "content_sha256": digest, "content_type": content_type,
        "state": "pending", "trust_level": "unverified", "created_at": created_at,
    }


def review_tenant_source_document(
    db: sqlite3.Connection, *, tenant_id: str, document_id: str,
    reviewer_id: str, decision: str, trust_level: str = "reviewed",
) -> dict[str, Any]:
    """Approve/reject a pending source with reviewer attribution from the caller's verified principal."""
    if decision not in {"approved", "rejected"}:
        raise ValueError("Source review decision must be approved or rejected.")
    if not isinstance(reviewer_id, str) or not reviewer_id.startswith("reviewer:"):
        raise ValueError("A server-derived verified reviewer identity is required.")
    if decision == "approved" and trust_level not in _ALLOWED_TRUST:
        raise ValueError("Approved sources require reviewed or authoritative trust.")
    if decision == "rejected":
        trust_level = "unverified"
    reviewed_at = _now()
    cursor = db.execute("""
      UPDATE tenant_approved_source_documents
      SET state=?, trust_level=?, reviewed_by=?, reviewed_at=?
      WHERE tenant_id=? AND document_id=? AND state='pending'
    """, (decision, trust_level, reviewer_id, reviewed_at, tenant_id, document_id))
    if cursor.rowcount != 1:
        raise ValueError("Pending source document was not found for this tenant.")
    row = db.execute("""
      SELECT document_id,title,uri,content_sha256,content_type,trust_level,
             state,reviewed_by,reviewed_at
      FROM tenant_approved_source_documents
      WHERE tenant_id=? AND document_id=?
    """, (tenant_id, document_id)).fetchone()
    return dict(row)


def get_approved_tenant_source_document(
    db: sqlite3.Connection, *, tenant_id: str, document_id: str,
) -> dict[str, Any] | None:
    """Return approved source content only within the authenticated tenant boundary."""
    row = db.execute("""
      SELECT tenant_id,document_id,title,uri,content,content_sha256,content_type,
             trust_level,state,reviewed_by,reviewed_at,created_at,metadata_json
      FROM tenant_approved_source_documents
      WHERE tenant_id=? AND document_id=? AND state='approved'
        AND trust_level IN ('reviewed','authoritative')
    """, (tenant_id, document_id)).fetchone()
    if row is None:
        return None
    document = dict(row)
    actual = hashlib.sha256(document["content"].encode("utf-8")).hexdigest()
    if actual != document["content_sha256"]:
        raise ValueError("Stored tenant source digest does not match its content.")
    document["metadata"] = json.loads(document.pop("metadata_json"))
    return document
