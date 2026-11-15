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
      evidence_json TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}', previous_hash TEXT NOT NULL,
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
    columns = {row[1] for row in db.execute("PRAGMA table_info(tenant_professor_reasoning_audit)")}
    if "metadata_json" not in columns:
        db.execute("ALTER TABLE tenant_professor_reasoning_audit ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}' ")


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
    metadata: dict
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
               model: str, evidence: list[dict], metadata: dict | None = None) -> ReasoningAuditRecord:
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
        safe_metadata = metadata or {}
        allowed_metadata = {"status", "step_count", "critique_accepted", "goal_coverage", "action_boundary", "execution_enabled", "memory_proposal_ids"}
        if not isinstance(safe_metadata, dict) or set(safe_metadata) - allowed_metadata:
            raise ValueError("Invalid reasoning trace metadata.")
        if safe_metadata.get("status") not in {None, "ready", "held_for_review", "needs_clarification"}:
            raise ValueError("Invalid reasoning status.")
        if safe_metadata.get("action_boundary") not in {None, "information_only", "draft_only", "human_approval_required"}:
            raise ValueError("Invalid action boundary.")
        if safe_metadata.get("step_count") is not None and (
            isinstance(safe_metadata["step_count"], bool) or not isinstance(safe_metadata["step_count"], int)
            or not 0 <= safe_metadata["step_count"] <= 16
        ):
            raise ValueError("Invalid reasoning step count.")
        if safe_metadata.get("critique_accepted") is not None and not isinstance(safe_metadata["critique_accepted"], bool):
            raise ValueError("Invalid critique status.")
        if safe_metadata.get("execution_enabled", False) is not False:
            raise ValueError("Reasoning trace cannot enable execution.")
        memory_ids = safe_metadata.get("memory_proposal_ids", [])
        if (not isinstance(memory_ids, list) or len(memory_ids) > 5
                or any(not isinstance(value, str) or not value.strip() or len(value) > 128
                       for value in memory_ids)
                or len(set(memory_ids)) != len(memory_ids)):
            raise ValueError("Invalid approved-memory trace references.")
        if safe_metadata.get("goal_coverage") is not None and (
            isinstance(safe_metadata["goal_coverage"], bool)
            or not isinstance(safe_metadata["goal_coverage"], (int, float))
            or not 0 <= safe_metadata["goal_coverage"] <= 1
        ):
            raise ValueError("Invalid goal coverage score.")
        metadata_encoded = json.dumps(safe_metadata, sort_keys=True, separators=(",", ":"), allow_nan=False)
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
            canonical_data = {
                "tenant_id": self.principal.tenant_id,
                "owner_key": self.owner_key,
                "conversation_id": conversation_id,
                "request_sha256": request_hash,
                "response_sha256": response_hash,
                "context_sha256": context_hash,
                "provider": provider, "model": model,
                "evidence": safe_evidence, "previous_hash": previous_hash,
            }
            if safe_metadata:
                canonical_data["metadata"] = safe_metadata
            canonical = json.dumps(canonical_data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            record_hash = self.digest(canonical)
            cur = self.db.execute(
                """INSERT INTO tenant_professor_reasoning_audit
                (tenant_id,owner_key,conversation_id,request_sha256,response_sha256,
                 context_sha256,provider,model,evidence_json,metadata_json,previous_hash,record_hash)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.principal.tenant_id, self.owner_key, conversation_id,
                 request_hash, response_hash, context_hash, provider, model,
                 encoded, metadata_encoded, previous_hash, record_hash),
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
            json.loads(row["metadata_json"]), row["previous_hash"], row["record_hash"], row["created_at"],
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

    def verify_chain(self):
        """Verify the complete tenant/owner hash chain without exposing raw content.

        The chain spans all conversations for this tenant/owner because append()
        links records at that scope. A valid result is tamper evidence, not proof
        against an attacker who can rewrite the entire database and its anchors.
        """
        self._authorize()
        rows = self.db.execute(
            """SELECT * FROM tenant_professor_reasoning_audit
               WHERE tenant_id=? AND owner_key=? ORDER BY audit_id ASC""",
            (self.principal.tenant_id, self.owner_key),
        ).fetchall()
        expected_previous = "0" * 64
        broken = []
        for row in rows:
            try:
                evidence = json.loads(row["evidence_json"])
                metadata = json.loads(row["metadata_json"])
                canonical_data = {
                    "tenant_id": row["tenant_id"],
                    "owner_key": row["owner_key"],
                    "conversation_id": row["conversation_id"],
                    "request_sha256": row["request_sha256"],
                    "response_sha256": row["response_sha256"],
                    "context_sha256": row["context_sha256"],
                    "provider": row["provider"], "model": row["model"],
                    "evidence": evidence, "previous_hash": row["previous_hash"],
                }
                if metadata:
                    canonical_data["metadata"] = metadata
                canonical = json.dumps(canonical_data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                calculated = self.digest(canonical)
                valid = (
                    row["previous_hash"] == expected_previous
                    and row["record_hash"] == calculated
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                valid = False
            if not valid:
                broken.append(row["audit_id"])
            expected_previous = row["record_hash"]
        return {
            "valid": not broken,
            "records_checked": len(rows),
            "broken_audit_ids": broken,
            "scope": "current_tenant_and_owner",
            "raw_content_checked": False,
        }
