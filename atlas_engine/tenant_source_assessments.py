"""Append-only, tenant-scoped source-status assessments.

These are attributed human review records, not machine quality scores. Unknown
must remain an allowed value; absence of a retraction notice is not proof that
a work has never been retracted.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

PUBLICATION_STATUSES = {"published", "preprint", "unpublished", "unknown"}
RETRACTION_STATUSES = {
    "not_known", "correction_notice", "expression_of_concern", "retracted", "unknown",
}
STUDY_DESIGNS = {
    "randomized_trial", "observational", "systematic_review", "meta_analysis",
    "case_report", "qualitative", "guideline", "other", "unknown",
}
MAX_EVIDENCE_REFERENCES = 10
MAX_RATIONALE_CHARS = 4000


def _valid_https_reference(value: str) -> bool:
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https" and bool(parsed.hostname)
            and parsed.username is None and parsed.password is None
            and parsed.port in (None, 443) and not parsed.fragment
        )
    except ValueError:
        return False


def initialize_tenant_source_assessment_schema(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS tenant_source_assessments (
      tenant_id TEXT NOT NULL,
      assessment_id TEXT NOT NULL,
      document_id TEXT NOT NULL,
      publication_status TEXT NOT NULL CHECK(publication_status IN
        ('published','preprint','unpublished','unknown')),
      retraction_status TEXT NOT NULL CHECK(retraction_status IN
        ('not_known','correction_notice','expression_of_concern','retracted','unknown')),
      study_design TEXT NOT NULL CHECK(study_design IN
        ('randomized_trial','observational','systematic_review','meta_analysis',
         'case_report','qualitative','guideline','other','unknown')),
      evidence_references_json TEXT NOT NULL,
      rationale TEXT NOT NULL,
      reviewer_id TEXT NOT NULL,
      assessed_at TEXT NOT NULL,
      supersedes_assessment_id TEXT,
      revision_reason TEXT,
      PRIMARY KEY(tenant_id, assessment_id),
      FOREIGN KEY(tenant_id, document_id)
        REFERENCES tenant_approved_source_documents(tenant_id, document_id)
    );
    CREATE INDEX IF NOT EXISTS idx_tenant_source_assessments_history
      ON tenant_source_assessments(tenant_id, document_id, assessed_at DESC);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_tenant_source_assessment_one_successor
      ON tenant_source_assessments(tenant_id, supersedes_assessment_id)
      WHERE supersedes_assessment_id IS NOT NULL;
    CREATE TRIGGER IF NOT EXISTS tenant_source_assessment_no_update
      BEFORE UPDATE ON tenant_source_assessments BEGIN
      SELECT RAISE(ABORT, 'source assessments are append-only');
    END;
    CREATE TRIGGER IF NOT EXISTS tenant_source_assessment_no_delete
      BEFORE DELETE ON tenant_source_assessments BEGIN
      SELECT RAISE(ABORT, 'source assessments are append-only');
    END;
    """)
    columns = {
        row["name"] for row in db.execute("PRAGMA table_info(tenant_source_assessments)")
    }
    if "supersedes_assessment_id" not in columns:
        db.execute("ALTER TABLE tenant_source_assessments ADD COLUMN supersedes_assessment_id TEXT")
    if "revision_reason" not in columns:
        db.execute("ALTER TABLE tenant_source_assessments ADD COLUMN revision_reason TEXT")
    db.execute("""
      CREATE UNIQUE INDEX IF NOT EXISTS idx_tenant_source_assessment_one_successor
      ON tenant_source_assessments(tenant_id, supersedes_assessment_id)
      WHERE supersedes_assessment_id IS NOT NULL
    """)


def append_tenant_source_assessment(
    db: sqlite3.Connection, *, tenant_id: str, document_id: str,
    reviewer_id: str, publication_status: str = "unknown",
    retraction_status: str = "unknown", study_design: str = "unknown",
    evidence_references: list[str] | None = None, rationale: str,
    supersedes_assessment_id: str | None = None,
    revision_reason: str | None = None,
) -> dict:
    """Append an assessment for an approved source; caller must pass verified reviewer attribution."""
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("Tenant identity is required.")
    if not isinstance(document_id, str) or not document_id.strip():
        raise ValueError("Source document identity is required.")
    if not isinstance(reviewer_id, str) or not reviewer_id.startswith("reviewer:"):
        raise ValueError("A server-derived reviewer identity is required.")
    if publication_status not in PUBLICATION_STATUSES:
        raise ValueError("Publication status is invalid.")
    if retraction_status not in RETRACTION_STATUSES:
        raise ValueError("Retraction status is invalid.")
    if study_design not in STUDY_DESIGNS:
        raise ValueError("Study design is invalid.")
    if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > MAX_RATIONALE_CHARS:
        raise ValueError("Assessment rationale must contain 1 to 4,000 characters.")
    refs = evidence_references or []
    if not isinstance(refs, list) or len(refs) > MAX_EVIDENCE_REFERENCES:
        raise ValueError("At most 10 evidence references may be supplied.")
    if any(not _valid_https_reference(ref) for ref in refs):
        raise ValueError("Assessment evidence references must be absolute HTTPS URLs.")
    encoded = json.dumps(refs, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if (supersedes_assessment_id is None) != (revision_reason is None):
        raise ValueError("A correction requires both supersedes_assessment_id and revision_reason.")
    if supersedes_assessment_id is not None:
        if not isinstance(supersedes_assessment_id, str) or not supersedes_assessment_id.strip():
            raise ValueError("Superseded assessment identifier is invalid.")
        if not isinstance(revision_reason, str) or not revision_reason.strip() or len(revision_reason) > 1000:
            raise ValueError("Correction reason must contain 1 to 1,000 characters.")
        target = db.execute("""
          SELECT document_id FROM tenant_source_assessments
          WHERE tenant_id=? AND assessment_id=?
        """, (tenant_id, supersedes_assessment_id)).fetchone()
        if target is None or target["document_id"] != document_id:
            raise ValueError("Superseded assessment was not found for this tenant and source.")
        existing_successor = db.execute("""
          SELECT 1 FROM tenant_source_assessments
          WHERE tenant_id=? AND supersedes_assessment_id=?
        """, (tenant_id, supersedes_assessment_id)).fetchone()
        if existing_successor is not None:
            raise ValueError("Assessment has already been superseded.")
    source = db.execute("""
      SELECT 1 FROM tenant_approved_source_documents
      WHERE tenant_id=? AND document_id=? AND state='approved'
        AND trust_level IN ('reviewed','authoritative')
    """, (tenant_id, document_id)).fetchone()
    if source is None:
        raise ValueError("Approved source document was not found for this tenant.")
    assessment_id = "sass_" + uuid.uuid4().hex
    assessed_at = datetime.now(timezone.utc).isoformat()
    db.execute("""
      INSERT INTO tenant_source_assessments
        (tenant_id,assessment_id,document_id,publication_status,retraction_status,
         study_design,evidence_references_json,rationale,reviewer_id,assessed_at,
         supersedes_assessment_id,revision_reason)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
    """, (tenant_id, assessment_id, document_id, publication_status,
          retraction_status, study_design, encoded, rationale.strip(),
          reviewer_id, assessed_at, supersedes_assessment_id,
          revision_reason.strip() if revision_reason else None))
    return {
        "assessment_id": assessment_id, "document_id": document_id,
        "publication_status": publication_status,
        "retraction_status": retraction_status, "study_design": study_design,
        "evidence_references": refs, "rationale": rationale.strip(),
        "reviewer_id": reviewer_id, "assessed_at": assessed_at,
        "supersedes_assessment_id": supersedes_assessment_id,
        "revision_reason": revision_reason.strip() if revision_reason else None,
        "quality_score": "not_scored",
    }


def list_tenant_source_assessments(
    db: sqlite3.Connection, *, tenant_id: str, document_id: str,
) -> list[dict]:
    """Return assessment history only for the requested tenant and source."""
    rows = db.execute("""
      SELECT assessment_id,document_id,publication_status,retraction_status,
             study_design,evidence_references_json,rationale,reviewer_id,assessed_at,
             supersedes_assessment_id,revision_reason
      FROM tenant_source_assessments
      WHERE tenant_id=? AND document_id=?
      ORDER BY assessed_at, assessment_id
    """, (tenant_id, document_id)).fetchall()
    superseded_by = {
        row["supersedes_assessment_id"]: row["assessment_id"]
        for row in rows if row["supersedes_assessment_id"] is not None
    }
    return [{
        "assessment_id": row["assessment_id"],
        "document_id": row["document_id"],
        "publication_status": row["publication_status"],
        "retraction_status": row["retraction_status"],
        "study_design": row["study_design"],
        "evidence_references": json.loads(row["evidence_references_json"]),
        "rationale": row["rationale"], "reviewer_id": row["reviewer_id"],
        "assessed_at": row["assessed_at"],
        "supersedes_assessment_id": row["supersedes_assessment_id"],
        "revision_reason": row["revision_reason"],
        "status": "superseded" if row["assessment_id"] in superseded_by else "active",
        "superseded_by": superseded_by.get(row["assessment_id"]),
        "quality_score": "not_scored",
    } for row in rows]
