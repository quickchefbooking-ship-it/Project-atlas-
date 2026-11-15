"""Append-only, tenant-scoped reasoning trace metadata for Professor.

Only hashes, provider metadata and bounded evidence provenance are stored.
Raw prompts, answers, credentials and retrieved excerpts are deliberately omitted.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from .identity_policy import RequestPrincipal, authorize_tenant_resource

MAX_EVIDENCE_ITEMS = 3
MAX_TRACE_LIMIT = 100


def initialize_reasoning_audit_schema(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS tenant_professor_reasoning_audit (
      audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
      tenant_id TEXT NOT NULL, owner_key TEXT NOT NULL,
      conversation_id TEXT NOT NULL,
      request_sha256 TEXT NOT NULL, response_sha256 TEXT NOT NULL,
      context_sha256 TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
      evidence_json TEXT NOT NULL, previous_hash TEXT NOT NULL,
      record_hash TEXT NOT NULL UNIQUE,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_professor_reasoning_audit_owner
      ON tenant_professor_reasoning_audit(tenant_id,owner_key,conversation_id,audit_id DESC);
    CREATE TRIGGER IF NOT EXISTS professor_reasoning_audit_no_update
      BEFORE UPDATE ON tenant_professor_reasoning_audit BEGIN
      SELECT RAISE(ABORT,'reasoning audit is append-only');
    END;
    CREATE TRIGGER IF NOT EXISTS professor_reasoning_audit_no_delete
      BEFORE DELETE ON tenant_professor_reasoning_audit BEGIN
      SELECT RAISE(ABORT,'reasoning audit is append-only');
    END;
    """)


@dataclass(frozen=True)
class ReasoningAuditRecord:
    audit_id: int
    conversation_id: str
    request_sha256: str
    response_sha256: str
    context_sha256: str
    provider: str
    model: str
    evidence: tuple[dict, ...]
    previous_hash: str
    record_hash: str
    created_at: str


class TenantReasoningAuditRepository:
    def __init__(self, db: sqlite3.Connection, principal: RequestPrincipal):
        if not isinstance(principal, RequestPrincipal):
            raise TypeError("A verified RequestPrincipal is required.")
        self.db = db
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.principal = principal
        self.owner_key = hashlib.sha256(
            (principal.issuer + "\0" + principal.subject).encode("utf-8")
        ).hexdigest()

    def _authorize(self):
        authorize_tenant_resource(self.principal, self.principal.tenant_id, {"conversations:read", "conversations:write"})

    @staticmethod
    def digest(value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Audit input must be text.")
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def append(self, *, conversation_id: str, request_text: str,
               response_text: str, context_text: str, provider: str,
               model: str, evidence: list[dict]) -> ReasoningAuditRecord:
        self._authorize()
        if not isinstance(conversation_id, str) or not conversation_id.strip() or len(conversation_id) > 128:
            raise ValueError("Invalid conversation identifier.")
        for name, value, maximum in (("provider", provider, 64), ("model", model, 128)):
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise ValueError(f"Invalid {name} metadata.")
        if not isinstance(evidence, list) or len(evidence) > MAX_EVIDENCE_ITEMS:
            raise ValueError("Evidence metadata exceeds the audit limit.")
        safe_evidence = []
        for item in evidence:
            if not isinstance(item, dict):
                raise ValueError("Invalid evidence metadata.")
            safe = {key: item.get(key, "") for key in ("document_id", "url", "content_sha256", "trust_level")}
            if any(not isinstance(value, str) or len(value) > 1000 for value in safe.values()):
                raise ValueError("Invalid evidence provenance.")
            safe_evidence.append(safe)
        request_hash = self.digest(request_text)
        response_hash = self.digest(response_text)
        context_hash = self.digest(context_text)
        encoded = json.dumps(safe_evidence, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            previous = self.db.execute(
                """SELECT record_hash FROM tenant_professor_reasoning_audit
                   WHERE tenant_id=? AND owner_key=? ORDER BY audit_id DESC LIMIT 1""",
                (self.principal.tenant_id, self.owner_key),
            ).fetchone()
            previous_hash = previous["record_hash"] if previous else "0" * 64
            canonical = json.dumps({
                "tenant_id": self.principal.tenant_id,
                "owner_key": self.owner_key,
                "conversation_id": conversation_id,
                "request_sha256": request_hash,
                "response_sha256": response_hash,
                "context_sha256": context_hash,
                "provider": provider, "model": model,
                "evidence": safe_evidence, "previous_hash": previous_hash,
            }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            record_hash = self.digest(canonical)
            cur = self.db.execute(
                """INSERT INTO tenant_professor_reasoning_audit
                (tenant_id,owner_key,conversation_id,request_sha256,response_sha256,
                 context_sha256,provider,model,evidence_json,previous_hash,record_hash)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (self.principal.tenant_id, self.owner_key, conversation_id,
                 request_hash, response_hash, context_hash, provider, model,
                 encoded, previous_hash, record_hash),
            )
            row = self.db.execute(
                "SELECT * FROM tenant_professor_reasoning_audit WHERE audit_id=?",
                (cur.lastrowid,),
            ).fetchone()
        return self._decode(row)

    @staticmethod
    def _decode(row):
        return ReasoningAuditRecord(
            row["audit_id"], row["conversation_id"], row["request_sha256"],
            row["response_sha256"], row["context_sha256"], row["provider"],
            row["model"], tuple(json.loads(row["evidence_json"])),
            row["previous_hash"], row["record_hash"], row["created_at"],
        )

    def list(self, conversation_id: str, *, limit: int = 50):
        self._authorize()
        if not isinstance(conversation_id, str) or not conversation_id.strip() or len(conversation_id) > 128:
            raise ValueError("Invalid conversation identifier.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_TRACE_LIMIT:
            raise ValueError("limit must be between 1 and 100.")
        rows = self.db.execute(
            """SELECT * FROM tenant_professor_reasoning_audit
               WHERE tenant_id=? AND owner_key=? AND conversation_id=?
               ORDER BY audit_id DESC LIMIT ?""",
            (self.principal.tenant_id, self.owner_key, conversation_id, limit),
        ).fetchall()
        return tuple(self._decode(row) for row in reversed(rows))
