"""Isolated tenant-owned learning and proposal records.

These prototype tables are separate from Professor's live schema. They use
composite tenant/parent foreign keys so a child record cannot be attached to
a task owned by another tenant.
"""
import json
import sqlite3

from .identity_policy import RequestPrincipal, authorize_tenant_resource
from .tenant_repository_prototype import TenantTaskNotFound


def initialize_learning_schema(connection: sqlite3.Connection) -> None:
    """Create tenant-scoped evaluation, lesson and proposal tables."""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS tenant_evaluations (
            evaluation_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            task_id INTEGER NOT NULL,
            passed INTEGER NOT NULL CHECK(passed IN (0, 1)),
            score REAL NOT NULL CHECK(score >= 0 AND score <= 1),
            reasons_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (tenant_id, evaluation_id),
            FOREIGN KEY (tenant_id, task_id)
                REFERENCES tenant_tasks (tenant_id, task_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS tenant_lessons (
            lesson_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            task_id INTEGER NOT NULL,
            summary TEXT NOT NULL,
            validated INTEGER NOT NULL DEFAULT 0 CHECK(validated IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (tenant_id, lesson_id),
            FOREIGN KEY (tenant_id, task_id)
                REFERENCES tenant_tasks (tenant_id, task_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS tenant_proposals (
            proposal_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            task_id INTEGER NOT NULL,
            problem TEXT NOT NULL,
            proposed_change TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected', 'tested')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (tenant_id, proposal_id),
            FOREIGN KEY (tenant_id, task_id)
                REFERENCES tenant_tasks (tenant_id, task_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_tenant_evaluations_task
            ON tenant_evaluations(tenant_id, task_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_tenant_lessons_task
            ON tenant_lessons(tenant_id, task_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_tenant_proposals_task
            ON tenant_proposals(tenant_id, task_id, created_at);
        """
    )


class TenantLearningRepository:
    """Tenant-filtered access to evaluations, lessons and improvement proposals."""

    def __init__(self, connection: sqlite3.Connection, principal: RequestPrincipal):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("A caller-owned SQLite connection is required.")
        if not isinstance(principal, RequestPrincipal):
            raise TypeError("A verified RequestPrincipal is required.")
        self._connection = connection
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._principal = principal

    def _require_task(self, task_id: int, scope: str) -> None:
        authorize_tenant_resource(self._principal, self._principal.tenant_id, {scope})
        row = self._connection.execute(
            "SELECT 1 FROM tenant_tasks WHERE tenant_id = ? AND task_id = ?",
            (self._principal.tenant_id, task_id),
        ).fetchone()
        if row is None:
            raise TenantTaskNotFound("Task was not found.")

    def add_evaluation(self, evaluation_id: str, task_id: int, passed: bool,
                       score: float, reasons) -> None:
        self._require_task(task_id, "evaluations:write")
        if not isinstance(evaluation_id, str) or not evaluation_id.strip():
            raise ValueError("evaluation_id is required.")
        if not isinstance(passed, bool) or isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
            raise ValueError("passed and score are invalid.")
        reasons_json = json.dumps(list(reasons), ensure_ascii=False, separators=(",", ":"))
        with self._connection:
            self._connection.execute(
                """INSERT INTO tenant_evaluations
                   (evaluation_id, tenant_id, task_id, passed, score, reasons_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (evaluation_id, self._principal.tenant_id, task_id, int(passed), float(score), reasons_json),
            )

    def list_evaluations(self, task_id: int) -> list:
        self._require_task(task_id, "evaluations:read")
        rows = self._connection.execute(
            """SELECT evaluation_id, tenant_id, task_id, passed, score, reasons_json, created_at
               FROM tenant_evaluations WHERE tenant_id = ? AND task_id = ?
               ORDER BY created_at, evaluation_id""",
            (self._principal.tenant_id, task_id),
        ).fetchall()
        return [{**dict(row), "reasons": json.loads(row["reasons_json"])} for row in rows]

    def add_lesson(self, lesson_id: str, task_id: int, summary: str,
                   validated: bool = False) -> None:
        self._require_task(task_id, "lessons:write")
        if not isinstance(lesson_id, str) or not lesson_id.strip() or not isinstance(summary, str) or not summary.strip():
            raise ValueError("lesson_id and summary are required.")
        if not isinstance(validated, bool):
            raise ValueError("validated must be a boolean.")
        with self._connection:
            self._connection.execute(
                """INSERT INTO tenant_lessons
                   (lesson_id, tenant_id, task_id, summary, validated)
                   VALUES (?, ?, ?, ?, ?)""",
                (lesson_id, self._principal.tenant_id, task_id, summary.strip(), int(validated)),
            )

    def list_lessons(self, task_id: int) -> list:
        self._require_task(task_id, "lessons:read")
        rows = self._connection.execute(
            """SELECT lesson_id, tenant_id, task_id, summary, validated, created_at
               FROM tenant_lessons WHERE tenant_id = ? AND task_id = ?
               ORDER BY created_at, lesson_id""",
            (self._principal.tenant_id, task_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def add_proposal(self, proposal_id: str, task_id: int, problem: str,
                     proposed_change: str) -> None:
        self._require_task(task_id, "proposals:write")
        if not all(isinstance(v, str) and v.strip() for v in (proposal_id, problem, proposed_change)):
            raise ValueError("proposal_id, problem and proposed_change are required.")
        with self._connection:
            self._connection.execute(
                """INSERT INTO tenant_proposals
                   (proposal_id, tenant_id, task_id, problem, proposed_change, status)
                   VALUES (?, ?, ?, ?, ?, 'pending')""",
                (proposal_id, self._principal.tenant_id, task_id, problem.strip(), proposed_change.strip()),
            )

    def list_proposals(self, task_id: int) -> list:
        self._require_task(task_id, "proposals:read")
        rows = self._connection.execute(
            """SELECT proposal_id, tenant_id, task_id, problem, proposed_change, status, created_at
               FROM tenant_proposals WHERE tenant_id = ? AND task_id = ?
               ORDER BY created_at, proposal_id""",
            (self._principal.tenant_id, task_id),
        ).fetchall()
        return [dict(row) for row in rows]
