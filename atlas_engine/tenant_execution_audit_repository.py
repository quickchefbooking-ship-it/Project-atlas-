"""Append-only, tenant-scoped audit reservations for Professor capability dispatch.

A committed reservation must exist before a capability handler is invoked.
The log stores identifiers and hashes, not raw prompts, inputs or outputs.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .identity_policy import RequestPrincipal, authorize_tenant_resource


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def initialize_execution_audit_schema(db: sqlite3.Connection) -> None:
    """Create append-only audit events in the existing tenant database."""
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS tenant_professor_execution_audit (
      event_id INTEGER PRIMARY KEY AUTOINCREMENT,
      tenant_id TEXT NOT NULL,
      actor_issuer TEXT NOT NULL,
      actor_subject TEXT NOT NULL,
      plan_id TEXT NOT NULL,
      step_id TEXT NOT NULL,
      capability TEXT NOT NULL,
      capability_version TEXT NOT NULL,
      attempt_number INTEGER NOT NULL CHECK(attempt_number > 0),
      fencing_token INTEGER NOT NULL CHECK(fencing_token > 0),
      reservation_event_id INTEGER,
      event_type TEXT NOT NULL CHECK(event_type IN
        ('execution_reserved','handler_succeeded','handler_failed')),
      input_sha256 TEXT,
      output_sha256 TEXT,
      details_json TEXT NOT NULL,
      created_at TEXT NOT NULL,
      FOREIGN KEY(reservation_event_id)
        REFERENCES tenant_professor_execution_audit(event_id) ON DELETE RESTRICT
    );
    CREATE INDEX IF NOT EXISTS idx_professor_execution_audit_tenant_plan
      ON tenant_professor_execution_audit(tenant_id,plan_id,event_id);
    CREATE TRIGGER IF NOT EXISTS professor_execution_audit_no_update
      BEFORE UPDATE ON tenant_professor_execution_audit BEGIN
      SELECT RAISE(ABORT,'execution audit history is append-only');
    END;
    CREATE TRIGGER IF NOT EXISTS professor_execution_audit_no_delete
      BEFORE DELETE ON tenant_professor_execution_audit BEGIN
      SELECT RAISE(ABORT,'execution audit history is append-only');
    END;
    """)


class TenantExecutionAuditRepository:
    """Write-only append operations scoped to the verified tenant principal."""

    def __init__(self, db: sqlite3.Connection, principal: RequestPrincipal):
        if not isinstance(db, sqlite3.Connection):
            raise TypeError("A caller-owned SQLite connection is required.")
        if not isinstance(principal, RequestPrincipal):
            raise TypeError("A verified RequestPrincipal is required.")
        self.db = db
        self.principal = principal
        self.db.row_factory = sqlite3.Row
        initialize_execution_audit_schema(db)

    def reserve(
        self, *, plan_id: str, step_id: str, capability: str,
        capability_version: str, attempt_number: int, fencing_token: int,
        capability_input: Any,
    ) -> int:
        """Commit an execution reservation or raise before handler dispatch."""
        tenant_id = self.principal.tenant_id
        authorize_tenant_resource(self.principal, tenant_id, {"plans:execute"})
        input_hash = _canonical_hash(capability_input)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            cursor = self.db.execute("""
              INSERT INTO tenant_professor_execution_audit
                (tenant_id,actor_issuer,actor_subject,plan_id,step_id,
                 capability,capability_version,attempt_number,fencing_token,
                 event_type,input_sha256,details_json,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,'execution_reserved',?,'{}',?)
            """, (
                tenant_id, self.principal.issuer, self.principal.subject,
                plan_id, step_id, capability, capability_version,
                attempt_number, fencing_token, input_hash, _now_iso(),
            ))
            event_id = int(cursor.lastrowid)
            self.db.commit()
            return event_id
        except Exception:
            if self.db.in_transaction:
                self.db.rollback()
            raise

    def record_outcome(
        self, reservation_event_id: int, *, event_type: str,
        output: Any = None, error_code: str | None = None,
    ) -> None:
        """Append the handler outcome; never edits the original reservation."""
        if event_type not in {"handler_succeeded", "handler_failed"}:
            raise ValueError("Unsupported execution audit outcome.")
        if event_type == "handler_failed" and (
            not isinstance(error_code, str) or not error_code.strip() or len(error_code) > 128
        ):
            raise ValueError("A bounded error_code is required for failed outcomes.")
        if event_type == "handler_succeeded" and error_code is not None:
            raise ValueError("Successful outcomes cannot include an error_code.")
        output_hash = _canonical_hash(output) if event_type == "handler_succeeded" else None
        details = json.dumps(
            {"error_code": error_code} if error_code else {},
            sort_keys=True, separators=(",", ":"),
        )
        tenant_id = self.principal.tenant_id
        authorize_tenant_resource(self.principal, tenant_id, {"plans:execute"})
        self.db.execute("BEGIN IMMEDIATE")
        try:
            reservation = self.db.execute("""
              SELECT actor_issuer,actor_subject,plan_id,step_id,capability,
                     capability_version,attempt_number,fencing_token
              FROM tenant_professor_execution_audit
              WHERE event_id=? AND tenant_id=? AND event_type='execution_reserved'
            """, (reservation_event_id, tenant_id)).fetchone()
            if reservation is None:
                raise ValueError("Execution reservation was not found.")
            self.db.execute("""
              INSERT INTO tenant_professor_execution_audit
                (tenant_id,actor_issuer,actor_subject,plan_id,step_id,
                 capability,capability_version,attempt_number,fencing_token,
                 reservation_event_id,event_type,output_sha256,details_json,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                tenant_id, reservation["actor_issuer"], reservation["actor_subject"],
                reservation["plan_id"], reservation["step_id"], reservation["capability"],
                reservation["capability_version"], reservation["attempt_number"],
                reservation["fencing_token"], reservation_event_id, event_type,
                output_hash, details, _now_iso(),
            ))
            self.db.commit()
        except Exception:
            if self.db.in_transaction:
                self.db.rollback()
            raise
