"""Durable, tenant-scoped cancellation requests for Professor plan execution.

Requests are append-only and cannot be withdrawn by the worker. This module
records the stop signal; the worker runtime must check it before claim,
dispatch, checkpoints and completion.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .identity_policy import RequestPrincipal, authorize_tenant_resource


class CancellationPlanNotFound(LookupError):
    """The requested tenant plan does not exist."""


class CancellationPlanNotActive(RuntimeError):
    """Only ready or running plans can receive a cancellation request."""


@dataclass(frozen=True)
class CancellationRequest:
    tenant_id: str
    plan_id: str
    requested_by_issuer: str
    requested_by_subject: str
    reason: str
    requested_at: str


def initialize_cancellation_schema(db: sqlite3.Connection) -> None:
    """Create the durable stop-signal table and protect its history."""
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS tenant_professor_cancellation_requests (
      tenant_id TEXT NOT NULL,
      plan_id TEXT NOT NULL,
      requested_by_issuer TEXT NOT NULL,
      requested_by_subject TEXT NOT NULL,
      reason TEXT NOT NULL,
      requested_at TEXT NOT NULL,
      PRIMARY KEY(tenant_id,plan_id),
      FOREIGN KEY(tenant_id,plan_id)
        REFERENCES tenant_professor_plans(tenant_id,plan_id) ON DELETE RESTRICT
    );
    CREATE TRIGGER IF NOT EXISTS professor_cancellation_no_update
      BEFORE UPDATE ON tenant_professor_cancellation_requests BEGIN
      SELECT RAISE(ABORT,'cancellation requests are immutable');
    END;
    CREATE TRIGGER IF NOT EXISTS professor_cancellation_no_delete
      BEFORE DELETE ON tenant_professor_cancellation_requests BEGIN
      SELECT RAISE(ABORT,'cancellation requests are immutable');
    END;
    """)


class TenantPlanCancellationRepository:
    """Tenant-scoped durable cancellation signal; no execution or auto-replay."""

    def __init__(self, db: sqlite3.Connection, principal: RequestPrincipal):
        if not isinstance(db, sqlite3.Connection):
            raise TypeError("A caller-owned SQLite connection is required.")
        if not isinstance(principal, RequestPrincipal):
            raise TypeError("A verified RequestPrincipal is required.")
        self.db = db
        self.principal = principal
        self.db.row_factory = sqlite3.Row
        initialize_cancellation_schema(db)

    def request(self, plan_id: str, *, reason: str) -> CancellationRequest:
        authorize_tenant_resource(self.principal, self.principal.tenant_id, {"plans:write"})
        if not isinstance(plan_id, str) or not plan_id.strip() or len(plan_id) > 128:
            raise ValueError("plan_id must be a non-empty bounded string.")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
            raise ValueError("A non-empty cancellation reason of at most 500 characters is required.")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            plan = self.db.execute(
                "SELECT state FROM tenant_professor_plans WHERE tenant_id=? AND plan_id=?",
                (self.principal.tenant_id, plan_id),
            ).fetchone()
            if plan is None:
                raise CancellationPlanNotFound("Plan was not found.")
            if plan["state"] not in {"ready", "running"}:
                raise CancellationPlanNotActive("Only ready or running plans can be cancelled.")
            self.db.execute("""
              INSERT OR IGNORE INTO tenant_professor_cancellation_requests
                (tenant_id,plan_id,requested_by_issuer,requested_by_subject,reason,requested_at)
              VALUES(?,?,?,?,?,?)
            """, (
                self.principal.tenant_id, plan_id, self.principal.issuer,
                self.principal.subject, reason.strip(),
                datetime.now(timezone.utc).isoformat(),
            ))
            row = self.db.execute("""
              SELECT tenant_id,plan_id,requested_by_issuer,requested_by_subject,reason,requested_at
              FROM tenant_professor_cancellation_requests
              WHERE tenant_id=? AND plan_id=?
            """, (self.principal.tenant_id, plan_id)).fetchone()
            self.db.commit()
            return self._record(row)
        except Exception:
            if self.db.in_transaction:
                self.db.rollback()
            raise

    def is_requested(self, plan_id: str) -> bool:
        authorize_tenant_resource(self.principal, self.principal.tenant_id, {"steps:read"})
        if not isinstance(plan_id, str) or not plan_id.strip() or len(plan_id) > 128:
            raise ValueError("plan_id must be a non-empty bounded string.")
        exists = self.db.execute(
            "SELECT 1 FROM tenant_professor_plans WHERE tenant_id=? AND plan_id=?",
            (self.principal.tenant_id, plan_id),
        ).fetchone()
        if exists is None:
            raise CancellationPlanNotFound("Plan was not found.")
        return self.db.execute(
            "SELECT 1 FROM tenant_professor_cancellation_requests WHERE tenant_id=? AND plan_id=?",
            (self.principal.tenant_id, plan_id),
        ).fetchone() is not None

    @staticmethod
    def _record(row: sqlite3.Row) -> CancellationRequest:
        return CancellationRequest(
            row["tenant_id"], row["plan_id"], row["requested_by_issuer"],
            row["requested_by_subject"], row["reason"], row["requested_at"],
        )
