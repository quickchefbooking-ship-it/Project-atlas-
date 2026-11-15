"""Tenant-isolated, append-only evaluation and lesson records for Professor.

Records capture human feedback and observed outcomes. They are evidence for
later review, not instructions, policy updates, training data, or permission
grants. No automatic prompt or capability changes are performed here.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from .identity_policy import RequestPrincipal, authorize_tenant_resource

MAX_REFERENCE_CHARS = 128
MAX_NOTE_CHARS = 2_000
MAX_PAYLOAD_BYTES = 8_192
MAX_LIST_LIMIT = 100
VALID_OUTCOMES = frozenset({"helpful", "partially_helpful", "not_helpful", "successful", "unsuccessful", "unknown"})


class EvaluationNotFound(LookupError):
    """An evaluation record is not owned by this principal."""


@dataclass(frozen=True)
class EvaluationRecord:
    evaluation_id: int
    tenant_id: str
    owner_key: str
    subject_type: str
    subject_id: str
    outcome: str
    rating: int | None
    note: str
    evidence: tuple[dict[str, Any], ...]
    created_at: str


def initialize_tenant_evaluation_schema(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS tenant_professor_evaluations (
      evaluation_id INTEGER PRIMARY KEY AUTOINCREMENT,
      tenant_id TEXT NOT NULL, owner_key TEXT NOT NULL,
      subject_type TEXT NOT NULL CHECK(subject_type IN ('conversation','plan','task')),
      subject_id TEXT NOT NULL, outcome TEXT NOT NULL,
      rating INTEGER CHECK(rating IS NULL OR rating BETWEEN 1 AND 5),
      note TEXT NOT NULL, evidence_json TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_professor_evaluations_owner
      ON tenant_professor_evaluations(tenant_id,owner_key,evaluation_id DESC);
    CREATE INDEX IF NOT EXISTS idx_professor_evaluations_subject
      ON tenant_professor_evaluations(tenant_id,owner_key,subject_type,subject_id);
    CREATE TRIGGER IF NOT EXISTS professor_evaluations_no_update
      BEFORE UPDATE ON tenant_professor_evaluations BEGIN
      SELECT RAISE(ABORT,'evaluation history is append-only');
    END;
    CREATE TRIGGER IF NOT EXISTS professor_evaluations_no_delete
      BEFORE DELETE ON tenant_professor_evaluations BEGIN
      SELECT RAISE(ABORT,'evaluation history is append-only');
    END;
    """)


class TenantEvaluationRepository:
    """Append-only feedback records isolated by tenant and verified owner."""

    def __init__(self, db: sqlite3.Connection, principal: RequestPrincipal):
        if not isinstance(db, sqlite3.Connection):
            raise TypeError("A caller-owned SQLite connection is required.")
        if not isinstance(principal, RequestPrincipal):
            raise TypeError("A verified RequestPrincipal is required.")
        self.db = db
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.principal = principal
        import hashlib
        self.owner_key = hashlib.sha256(
            (principal.issuer + "\0" + principal.subject).encode("utf-8")
        ).hexdigest()

    def _authorize(self, scope: str) -> None:
        authorize_tenant_resource(self.principal, self.principal.tenant_id, {scope})

    @staticmethod
    def _validate_reference(value: str, label: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_REFERENCE_CHARS:
            raise ValueError(f"{label} must be a non-empty string of at most 128 characters.")
        return value.strip()

    @staticmethod
    def _decode(row: sqlite3.Row) -> EvaluationRecord:
        return EvaluationRecord(
            evaluation_id=row["evaluation_id"], tenant_id=row["tenant_id"],
            owner_key=row["owner_key"], subject_type=row["subject_type"],
            subject_id=row["subject_id"], outcome=row["outcome"],
            rating=row["rating"], note=row["note"],
            evidence=tuple(json.loads(row["evidence_json"])),
            created_at=row["created_at"],
        )

    def record(self, *, subject_type: str, subject_id: str, outcome: str,
               rating: int | None = None, note: str = "",
               evidence: tuple[dict[str, Any], ...] | list[dict[str, Any]] = ()) -> EvaluationRecord:
        self._authorize("evaluations:write")
        subject_id = self._validate_reference(subject_id, "subject_id")
        if subject_type not in {"conversation", "plan", "task"}:
            raise ValueError("Unsupported evaluation subject_type.")
        if outcome not in VALID_OUTCOMES:
            raise ValueError("Unsupported evaluation outcome.")
        if rating is not None and (isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5):
            raise ValueError("rating must be an integer between 1 and 5.")
        if not isinstance(note, str) or len(note) > MAX_NOTE_CHARS:
            raise ValueError("note must be a string of at most 2000 characters.")
        if not isinstance(evidence, (tuple, list)) or len(evidence) > 10:
            raise ValueError("evidence must contain at most 10 items.")
        clean_evidence = []
        for item in evidence:
            if not isinstance(item, dict):
                raise ValueError("Each evidence reference must be an object.")
            allowed = {"document_id", "url", "content_sha256"}
            if set(item) - allowed:
                raise ValueError("Evidence may contain only provenance references.")
            clean_item = {}
            for key, value in item.items():
                maximum = 1_000 if key == "url" else (64 if key == "content_sha256" else MAX_REFERENCE_CHARS)
                if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                    raise ValueError(f"{key} must be a non-empty string of at most {maximum} characters.")
                clean_item[key] = value.strip()
            clean_evidence.append(clean_item)
        encoded = json.dumps(clean_evidence, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ValueError("Evidence references exceed the storage limit.")
        with self.db:
            cur = self.db.execute(
                """INSERT INTO tenant_professor_evaluations
                   (tenant_id,owner_key,subject_type,subject_id,outcome,rating,note,evidence_json)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (self.principal.tenant_id, self.owner_key, subject_type, subject_id,
                 outcome, rating, note.strip(), encoded),
            )
            row = self.db.execute(
                "SELECT * FROM tenant_professor_evaluations WHERE evaluation_id=?",
                (cur.lastrowid,),
            ).fetchone()
        return self._decode(row)

    def summary(self) -> dict[str, Any]:
        """Return bounded aggregate counts; never exposes notes or evidence content."""
        self._authorize("evaluations:read")
        rows = self.db.execute(
            """SELECT outcome, COUNT(*) AS total
               FROM tenant_professor_evaluations
               WHERE tenant_id=? AND owner_key=?
               GROUP BY outcome ORDER BY outcome""",
            (self.principal.tenant_id, self.owner_key),
        ).fetchall()
        counts = {outcome: 0 for outcome in sorted(VALID_OUTCOMES)}
        for row in rows:
            counts[row["outcome"]] = int(row["total"])
        total = sum(counts.values())
        rated = self.db.execute(
            """SELECT COUNT(*) AS total, AVG(rating) AS average
               FROM tenant_professor_evaluations
               WHERE tenant_id=? AND owner_key=? AND rating IS NOT NULL""",
            (self.principal.tenant_id, self.owner_key),
        ).fetchone()
        return {
            "total": total,
            "outcomes": counts,
            "rated_count": int(rated["total"]),
            "average_rating": round(float(rated["average"]), 2) if rated["average"] is not None else None,
            "interpretation": "Descriptive feedback only; not a verified measure of correctness or permission to change behaviour.",
        }

    def list(self, *, limit: int = 50, subject_type: str | None = None,
             subject_id: str | None = None) -> tuple[EvaluationRecord, ...]:
        self._authorize("evaluations:read")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIST_LIMIT:
            raise ValueError("limit must be between 1 and 100.")
        if subject_type is not None and subject_type not in {"conversation", "plan", "task"}:
            raise ValueError("Unsupported evaluation subject_type.")
        sql = """SELECT * FROM tenant_professor_evaluations
                 WHERE tenant_id=? AND owner_key=?"""
        args: list[Any] = [self.principal.tenant_id, self.owner_key]
        if subject_type is not None:
            sql += " AND subject_type=?"; args.append(subject_type)
        if subject_id is not None:
            sql += " AND subject_id=?"; args.append(self._validate_reference(subject_id, "subject_id"))
        sql += " ORDER BY evaluation_id DESC LIMIT ?"; args.append(limit)
        return tuple(self._decode(row) for row in self.db.execute(sql, args).fetchall())
