"""Isolated tenant-scoped task repository prototype.

This module is deliberately not wired into the live Professor application or
its existing database. It accepts a caller-owned SQLite connection so tests
and future integration work can use a disposable database first.
"""
import sqlite3
from typing import Optional

from .identity_policy import (
    AuthorizationDenied,
    RequestPrincipal,
    authorize_tenant_resource,
)


class TenantTaskNotFound(LookupError):
    """Task or child record is absent from the caller's tenant-visible view."""


def initialize_prototype_schema(connection: sqlite3.Connection) -> None:
    """Create isolated prototype tables; never run against the core app schema."""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS tenant_tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (tenant_id, task_id)
        );

        CREATE TABLE IF NOT EXISTS tenant_task_attempts (
            attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            task_id INTEGER NOT NULL,
            outcome TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id, task_id)
                REFERENCES tenant_tasks (tenant_id, task_id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_tenant_tasks_owner
            ON tenant_tasks (tenant_id, task_id);
        CREATE INDEX IF NOT EXISTS idx_tenant_attempts_owner_task
            ON tenant_task_attempts (tenant_id, task_id, attempt_id);
        """
    )


class TenantTaskRepository:
    """Minimal repository enforcing tenant predicates at the SQL boundary."""

    def __init__(self, connection: sqlite3.Connection, principal: RequestPrincipal):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("A caller-owned SQLite connection is required.")
        if not isinstance(principal, RequestPrincipal):
            raise AuthorizationDenied("Verified request principal required.")
        self._connection = connection
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._principal = principal

    def create_task(self, title: str) -> int:
        authorize_tenant_resource(self._principal, self._principal.tenant_id, {"tasks:write"})
        if not isinstance(title, str) or not title.strip() or len(title) > 500:
            raise ValueError("title must be a non-empty string of at most 500 characters.")
        with self._connection:
            cursor = self._connection.execute(
                "INSERT INTO tenant_tasks (tenant_id, title) VALUES (?, ?)",
                (self._principal.tenant_id, title.strip()),
            )
            return int(cursor.lastrowid)

    def get_task(self, task_id: int) -> dict:
        authorize_tenant_resource(self._principal, self._principal.tenant_id, {"tasks:read"})
        row = self._connection.execute(
            """SELECT task_id, tenant_id, title, created_at
               FROM tenant_tasks WHERE tenant_id = ? AND task_id = ?""",
            (self._principal.tenant_id, task_id),
        ).fetchone()
        if row is None:
            raise TenantTaskNotFound("Task was not found.")
        return dict(row)

    def list_tasks(self) -> list:
        authorize_tenant_resource(self._principal, self._principal.tenant_id, {"tasks:read"})
        rows = self._connection.execute(
            """SELECT task_id, tenant_id, title, created_at
               FROM tenant_tasks WHERE tenant_id = ? ORDER BY task_id""",
            (self._principal.tenant_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def create_attempt(self, task_id: int, outcome: str) -> int:
        authorize_tenant_resource(self._principal, self._principal.tenant_id, {"tasks:write"})
        if not isinstance(outcome, str) or not outcome.strip() or len(outcome) > 200:
            raise ValueError("outcome must be a non-empty string of at most 200 characters.")
        with self._connection:
            parent = self._connection.execute(
                """SELECT task_id FROM tenant_tasks
                   WHERE tenant_id = ? AND task_id = ?""",
                (self._principal.tenant_id, task_id),
            ).fetchone()
            if parent is None:
                raise TenantTaskNotFound("Task was not found.")
            cursor = self._connection.execute(
                """INSERT INTO tenant_task_attempts (tenant_id, task_id, outcome)
                   VALUES (?, ?, ?)""",
                (self._principal.tenant_id, task_id, outcome.strip()),
            )
            return int(cursor.lastrowid)

    def list_attempts(self, task_id: int) -> list:
        authorize_tenant_resource(self._principal, self._principal.tenant_id, {"tasks:read"})
        rows = self._connection.execute(
            """SELECT a.attempt_id, a.tenant_id, a.task_id, a.outcome, a.created_at
               FROM tenant_task_attempts AS a
               JOIN tenant_tasks AS t
                 ON t.tenant_id = a.tenant_id AND t.task_id = a.task_id
               WHERE a.tenant_id = ? AND a.task_id = ?
               ORDER BY a.attempt_id""",
            (self._principal.tenant_id, task_id),
        ).fetchall()
        # Match the parent lookup's not-found behavior for cross-tenant IDs.
        if not self._connection.execute(
            "SELECT 1 FROM tenant_tasks WHERE tenant_id = ? AND task_id = ?",
            (self._principal.tenant_id, task_id),
        ).fetchone():
            raise TenantTaskNotFound("Task was not found.")
        return [dict(row) for row in rows]
