"""Tenant- and owner-scoped durable memory with explicit approval.

Conversation history is working context, not durable knowledge. This repository
stores only user-proposed memories after an explicit approval decision. Retrieval
is bounded, expiry-aware and isolated by tenant and owner. No model may promote
or write memory directly.
"""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .identity_policy import RequestPrincipal, authorize_tenant_resource

MAX_MEMORY_TITLE_CHARS = 120
MAX_MEMORY_CONTENT_CHARS = 2_000
MAX_MEMORY_CATEGORY_CHARS = 64
MAX_MEMORY_LIMIT = 20
MAX_RETENTION_DAYS = 3_650


class MemoryNotFound(LookupError):
    """A memory record is not available to this owner."""


@dataclass(frozen=True)
class MemoryProposal:
    proposal_id: str
    category: str
    title: str
    content: str
    status: str
    expires_at: str
    created_at: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _owner_key(principal: RequestPrincipal) -> str:
    return hashlib.sha256(
        (principal.issuer + "\\0" + principal.subject).encode("utf-8")
    ).hexdigest()


def initialize_tenant_memory_schema(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS tenant_professor_memory_proposals (
      tenant_id TEXT NOT NULL,
      owner_key TEXT NOT NULL,
      proposal_id TEXT NOT NULL,
      category TEXT NOT NULL,
      title TEXT NOT NULL,
      content TEXT NOT NULL,
      status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected')),
      expires_at TEXT NOT NULL,
      created_at TEXT NOT NULL,
      PRIMARY KEY(tenant_id,owner_key,proposal_id)
    );
    CREATE INDEX IF NOT EXISTS idx_professor_memory_proposals
      ON tenant_professor_memory_proposals(tenant_id,owner_key,status,created_at DESC);
    CREATE TABLE IF NOT EXISTS tenant_professor_memory_decisions (
      decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
      tenant_id TEXT NOT NULL,
      owner_key TEXT NOT NULL,
      proposal_id TEXT NOT NULL,
      reviewer_key TEXT NOT NULL,
      decision TEXT NOT NULL CHECK(decision IN ('approved','rejected')),
      rationale TEXT NOT NULL,
      decided_at TEXT NOT NULL,
      FOREIGN KEY(tenant_id,owner_key,proposal_id)
        REFERENCES tenant_professor_memory_proposals(tenant_id,owner_key,proposal_id)
        ON DELETE RESTRICT
    );
    CREATE INDEX IF NOT EXISTS idx_professor_memory_decisions
      ON tenant_professor_memory_decisions(tenant_id,owner_key,proposal_id,decision_id);
    CREATE TRIGGER IF NOT EXISTS professor_memory_decisions_no_update
      BEFORE UPDATE ON tenant_professor_memory_decisions BEGIN
      SELECT RAISE(ABORT,'memory decision history is append-only');
    END;
    CREATE TRIGGER IF NOT EXISTS professor_memory_decisions_no_delete
      BEFORE DELETE ON tenant_professor_memory_decisions BEGIN
      SELECT RAISE(ABORT,'memory decision history is append-only');
    END;
    """)


class TenantProfessorMemoryRepository:
    """Explicitly approved durable memory, isolated to one tenant and owner."""

    def __init__(self, db: sqlite3.Connection, principal: RequestPrincipal):
        if not isinstance(db, sqlite3.Connection):
            raise TypeError("A caller-owned SQLite connection is required.")
        if not isinstance(principal, RequestPrincipal):
            raise TypeError("A verified RequestPrincipal is required.")
        self.db = db
        self.db.execute("PRAGMA foreign_keys=ON")
        self.principal = principal
        self.owner_key = _owner_key(principal)

    def _authorize(self, scope: str) -> None:
        authorize_tenant_resource(self.principal, self.principal.tenant_id, {scope})

    @staticmethod
    def _validate_text(value: str, field: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise ValueError(f"{field} must contain 1 to {maximum} characters.")
        return value.strip()

    def propose(self, proposal_id: str, *, category: str, title: str, content: str,
                retention_days: int = 90) -> MemoryProposal:
        self._authorize("memory:propose")
        proposal_id = self._validate_text(proposal_id, "proposal_id", 128)
        category = self._validate_text(category, "category", MAX_MEMORY_CATEGORY_CHARS)
        title = self._validate_text(title, "title", MAX_MEMORY_TITLE_CHARS)
        content = self._validate_text(content, "content", MAX_MEMORY_CONTENT_CHARS)
        if isinstance(retention_days, bool) or not isinstance(retention_days, int) or not 1 <= retention_days <= MAX_RETENTION_DAYS:
            raise ValueError(f"retention_days must be between 1 and {MAX_RETENTION_DAYS}.")
        now = _utc_now()
        created_at = now.isoformat()
        expires_at = (now + timedelta(days=retention_days)).isoformat()
        try:
            with self.db:
                self.db.execute(
                    """INSERT INTO tenant_professor_memory_proposals
                       (tenant_id,owner_key,proposal_id,category,title,content,status,expires_at,created_at)
                       VALUES(?,?,?,?,?,?,'pending',?,?)""",
                    (self.principal.tenant_id, self.owner_key, proposal_id,
                     category, title, content, expires_at, created_at),
                )
        except sqlite3.IntegrityError:
            raise ValueError("Memory proposal ID already exists.") from None
        return MemoryProposal(proposal_id, category, title, content, "pending", expires_at, created_at)

    def decide(self, proposal_id: str, *, decision: str, rationale: str = "") -> None:
        self._authorize("memory:approve")
        proposal_id = self._validate_text(proposal_id, "proposal_id", 128)
        if decision not in {"approved", "rejected"}:
            raise ValueError("Decision must be approved or rejected.")
        if not isinstance(rationale, str) or len(rationale) > 500:
            raise ValueError("Rationale must be at most 500 characters.")
        now = _utc_now().isoformat()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute(
                """SELECT status,expires_at FROM tenant_professor_memory_proposals
                   WHERE tenant_id=? AND owner_key=? AND proposal_id=?""",
                (self.principal.tenant_id, self.owner_key, proposal_id),
            ).fetchone()
            if row is None:
                raise MemoryNotFound("Memory proposal was not found.")
            if row["status"] != "pending":
                raise ValueError("Only pending memory proposals can be decided.")
            if row["expires_at"] <= now:
                raise ValueError("Expired memory proposals cannot be approved.")
            self.db.execute(
                """UPDATE tenant_professor_memory_proposals SET status=?
                   WHERE tenant_id=? AND owner_key=? AND proposal_id=?""",
                (decision, self.principal.tenant_id, self.owner_key, proposal_id),
            )
            self.db.execute(
                """INSERT INTO tenant_professor_memory_decisions
                   (tenant_id,owner_key,proposal_id,reviewer_key,decision,rationale,decided_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (self.principal.tenant_id, self.owner_key, proposal_id,
                 self.owner_key, decision, rationale.strip(), now),
            )

    def list_proposals(self, *, status: str = "pending", limit: int = 50) -> tuple[dict, ...]:
        self._authorize("memory:read")
        if status not in {"pending", "approved", "rejected", "all"}:
            raise ValueError("Invalid memory proposal status.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("Proposal limit must be between 1 and 200.")
        params: list[object] = [self.principal.tenant_id, self.owner_key]
        clause = ""
        if status != "all":
            clause = " AND status=?"
            params.append(status)
        params.append(limit)
        rows = self.db.execute(
            """SELECT proposal_id,category,title,content,status,expires_at,created_at
               FROM tenant_professor_memory_proposals
               WHERE tenant_id=? AND owner_key=?""" + clause +
            " ORDER BY created_at DESC,proposal_id LIMIT ?",
            params,
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def retrieve(self, query: str, *, limit: int = 5) -> tuple[dict, ...]:
        """Simple bounded lexical retrieval of approved, unexpired owner memories."""
        self._authorize("memory:read")
        query = self._validate_text(query, "query", 1_000).casefold()
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_MEMORY_LIMIT:
            raise ValueError(f"Memory retrieval limit must be between 1 and {MAX_MEMORY_LIMIT}.")
        terms = {word for word in query.split() if len(word) > 2}
        now = _utc_now().isoformat()
        rows = self.db.execute(
            """SELECT proposal_id,category,title,content,expires_at,created_at
               FROM tenant_professor_memory_proposals
               WHERE tenant_id=? AND owner_key=? AND status='approved' AND expires_at>?
               ORDER BY created_at DESC""",
            (self.principal.tenant_id, self.owner_key, now),
        ).fetchall()
        ranked = []
        for row in rows:
            haystack = (row["category"] + " " + row["title"] + " " + row["content"]).casefold()
            overlap = terms.intersection(set(haystack.split()))
            if overlap:
                ranked.append((len(overlap), row))
        ranked.sort(key=lambda item: (-item[0], item[1]["created_at"], item[1]["proposal_id"]))
        return tuple({
            **dict(row),
            "matched_terms": sorted(terms.intersection(set(
                (row["category"] + " " + row["title"] + " " + row["content"]).casefold().split()
            )))
        } for _score, row in ranked[:limit])

    def delete(self, proposal_id: str) -> None:
        """Delete an owner's memory content and linked decision details."""
        self._authorize("memory:delete")
        proposal_id = self._validate_text(proposal_id, "proposal_id", 128)
        with self.db:
            row = self.db.execute(
                """SELECT 1 FROM tenant_professor_memory_proposals
                   WHERE tenant_id=? AND owner_key=? AND proposal_id=?""",
                (self.principal.tenant_id, self.owner_key, proposal_id),
            ).fetchone()
            if row is None:
                raise MemoryNotFound("Memory item was not found.")
            self.db.execute(
                """DELETE FROM tenant_professor_memory_decisions
                   WHERE tenant_id=? AND owner_key=? AND proposal_id=?""",
                (self.principal.tenant_id, self.owner_key, proposal_id),
            )
            self.db.execute(
                """DELETE FROM tenant_professor_memory_proposals
                   WHERE tenant_id=? AND owner_key=? AND proposal_id=?""",
                (self.principal.tenant_id, self.owner_key, proposal_id),
            )
