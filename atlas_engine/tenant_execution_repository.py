"""Tenant-scoped execution history prototypes.

These tables are isolated from Professor's live database. Composite foreign
keys bind every attempt-linked record to the same tenant and task.
"""
import json
import sqlite3

from .identity_policy import RequestPrincipal, authorize_tenant_resource
from .tenant_repository_prototype import TenantTaskNotFound


def initialize_execution_schema(connection: sqlite3.Connection) -> None:
    """Create isolated recovery, cancellation, retry and lesson-use tables."""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS tenant_recovery_decisions (
            decision_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            task_id INTEGER NOT NULL,
            attempt_id INTEGER NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('mark_failed', 'retry')),
            reason TEXT NOT NULL,
            retry_safe INTEGER NOT NULL DEFAULT 0 CHECK(retry_safe IN (0, 1)),
            side_effects_reconciled INTEGER NOT NULL DEFAULT 0
                CHECK(side_effects_reconciled IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id, task_id, attempt_id)
                REFERENCES tenant_task_attempts (tenant_id, task_id, attempt_id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tenant_cancellations (
            cancellation_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            task_id INTEGER NOT NULL,
            attempt_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN
                ('requested', 'acknowledged', 'too_late', 'requires_recovery')),
            requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            acknowledged_at TEXT,
            UNIQUE (tenant_id, attempt_id),
            FOREIGN KEY (tenant_id, task_id, attempt_id)
                REFERENCES tenant_task_attempts (tenant_id, task_id, attempt_id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tenant_retry_schedules (
            schedule_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            task_id INTEGER NOT NULL,
            originating_attempt_id INTEGER NOT NULL,
            next_attempt_number INTEGER NOT NULL CHECK(next_attempt_number > 0),
            due_at TEXT NOT NULL,
            deadline_at TEXT NOT NULL,
            capability_name TEXT NOT NULL,
            capability_version TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            error_code TEXT NOT NULL,
            policy_json TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN
                ('scheduled', 'claimed', 'cancelled', 'expired')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            claimed_at TEXT,
            claimed_attempt_id INTEGER,
            CHECK(deadline_at > due_at),
            UNIQUE (tenant_id, originating_attempt_id),
            FOREIGN KEY (tenant_id, task_id, originating_attempt_id)
                REFERENCES tenant_task_attempts (tenant_id, task_id, attempt_id)
                ON DELETE CASCADE,
            FOREIGN KEY (tenant_id, task_id, claimed_attempt_id)
                REFERENCES tenant_task_attempts (tenant_id, task_id, attempt_id)
        );

        CREATE TABLE IF NOT EXISTS tenant_lesson_usage_events (
            usage_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            task_id INTEGER NOT NULL,
            attempt_id INTEGER NOT NULL,
            lesson_id TEXT NOT NULL,
            recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (tenant_id, attempt_id, lesson_id),
            FOREIGN KEY (tenant_id, task_id, attempt_id)
                REFERENCES tenant_task_attempts (tenant_id, task_id, attempt_id)
                ON DELETE CASCADE,
            FOREIGN KEY (tenant_id, task_id, lesson_id)
                REFERENCES tenant_lessons (tenant_id, task_id, lesson_id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_tenant_recovery_task
            ON tenant_recovery_decisions(tenant_id, task_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_tenant_cancellations_task
            ON tenant_cancellations(tenant_id, task_id, requested_at);
        CREATE INDEX IF NOT EXISTS idx_tenant_retry_due
            ON tenant_retry_schedules(tenant_id, state, due_at, deadline_at);
        CREATE INDEX IF NOT EXISTS idx_tenant_lesson_usage_task
            ON tenant_lesson_usage_events(tenant_id, task_id, recorded_at);
        """
    )


def ensure_execution_parent_keys(connection: sqlite3.Connection) -> None:
    """Add composite unique keys required by tenant-consistent child FKs.

    Must be called after the task and learning prototype schemas are created.
    """
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_lessons_task_lesson
            ON tenant_lessons(tenant_id, task_id, lesson_id);
        """
    )


class TenantExecutionRepository:
    """Tenant-filtered writes and reads for execution lifecycle records."""

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

    def _require_attempt(self, task_id: int, attempt_id: int, scope: str) -> None:
        self._require_task(task_id, scope)
        row = self._connection.execute(
            """SELECT 1 FROM tenant_task_attempts
               WHERE tenant_id = ? AND task_id = ? AND attempt_id = ?""",
            (self._principal.tenant_id, task_id, attempt_id),
        ).fetchone()
        if row is None:
            raise TenantTaskNotFound("Attempt was not found.")

    def add_recovery_decision(self, decision_id: str, task_id: int, attempt_id: int,
                              action: str, reason: str, retry_safe: bool = False,
                              side_effects_reconciled: bool = False) -> None:
        self._require_attempt(task_id, attempt_id, "tasks:write")
        if not decision_id.strip() or not reason.strip():
            raise ValueError("decision_id and reason are required.")
        if action not in {"mark_failed", "retry"}:
            raise ValueError("Unsupported recovery action.")
        if not isinstance(retry_safe, bool) or not isinstance(side_effects_reconciled, bool):
            raise ValueError("Recovery flags must be booleans.")
        with self._connection:
            self._connection.execute(
                """INSERT INTO tenant_recovery_decisions
                   (decision_id, tenant_id, task_id, attempt_id, action, reason,
                    retry_safe, side_effects_reconciled)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (decision_id, self._principal.tenant_id, task_id, attempt_id,
                 action, reason.strip(), int(retry_safe), int(side_effects_reconciled)),
            )

    def list_recovery_decisions(self, task_id: int) -> list:
        self._require_task(task_id, "tasks:read")
        rows = self._connection.execute(
            """SELECT * FROM tenant_recovery_decisions
               WHERE tenant_id = ? AND task_id = ? ORDER BY created_at, decision_id""",
            (self._principal.tenant_id, task_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def add_cancellation(self, cancellation_id: str, task_id: int, attempt_id: int,
                         reason: str, state: str = "requested") -> None:
        self._require_attempt(task_id, attempt_id, "tasks:write")
        if not cancellation_id.strip() or not reason.strip():
            raise ValueError("cancellation_id and reason are required.")
        if state not in {"requested", "acknowledged", "too_late", "requires_recovery"}:
            raise ValueError("Unsupported cancellation state.")
        acknowledged_at = None
        if state == "acknowledged":
            acknowledged_at = "CURRENT_TIMESTAMP"
        with self._connection:
            self._connection.execute(
                """INSERT INTO tenant_cancellations
                   (cancellation_id, tenant_id, task_id, attempt_id, reason, state,
                    acknowledged_at)
                   VALUES (?, ?, ?, ?, ?, ?, CASE WHEN ? = 'acknowledged'
                       THEN CURRENT_TIMESTAMP ELSE NULL END)""",
                (cancellation_id, self._principal.tenant_id, task_id, attempt_id,
                 reason.strip(), state, state),
            )

    def list_cancellations(self, task_id: int) -> list:
        self._require_task(task_id, "tasks:read")
        rows = self._connection.execute(
            """SELECT * FROM tenant_cancellations
               WHERE tenant_id = ? AND task_id = ? ORDER BY requested_at, cancellation_id""",
            (self._principal.tenant_id, task_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def add_retry_schedule(self, schedule_id: str, task_id: int, originating_attempt_id: int,
                           next_attempt_number: int, due_at: str, deadline_at: str,
                           capability_name: str, capability_version: str,
                           idempotency_key: str, error_code: str, policy: dict) -> None:
        self._require_attempt(task_id, originating_attempt_id, "tasks:write")
        if not all(isinstance(v, str) and v.strip() for v in
                   (schedule_id, due_at, deadline_at, capability_name,
                    capability_version, idempotency_key, error_code)):
            raise ValueError("Retry schedule identifiers and timestamps are required.")
        if isinstance(next_attempt_number, bool) or not isinstance(next_attempt_number, int) or next_attempt_number < 1:
            raise ValueError("next_attempt_number must be a positive integer.")
        if deadline_at <= due_at:
            raise ValueError("deadline_at must be later than due_at.")
        if not isinstance(policy, dict):
            raise ValueError("policy must be an object.")
        with self._connection:
            self._connection.execute(
                """INSERT INTO tenant_retry_schedules
                   (schedule_id, tenant_id, task_id, originating_attempt_id,
                    next_attempt_number, due_at, deadline_at, capability_name,
                    capability_version, idempotency_key, error_code, policy_json, state)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled')""",
                (schedule_id, self._principal.tenant_id, task_id, originating_attempt_id,
                 next_attempt_number, due_at, deadline_at, capability_name,
                 capability_version, idempotency_key, error_code,
                 json.dumps(policy, sort_keys=True, separators=(",", ":"))),
            )

    def list_retry_schedules(self, task_id: int) -> list:
        self._require_task(task_id, "tasks:read")
        rows = self._connection.execute(
            """SELECT * FROM tenant_retry_schedules
               WHERE tenant_id = ? AND task_id = ? ORDER BY created_at, schedule_id""",
            (self._principal.tenant_id, task_id),
        ).fetchall()
        return [{**dict(row), "policy": json.loads(row["policy_json"])} for row in rows]

    def record_lesson_use(self, usage_id: str, task_id: int, attempt_id: int,
                          lesson_id: str) -> None:
        self._require_attempt(task_id, attempt_id, "lessons:write")
        lesson = self._connection.execute(
            """SELECT 1 FROM tenant_lessons
               WHERE tenant_id = ? AND task_id = ? AND lesson_id = ?""",
            (self._principal.tenant_id, task_id, lesson_id),
        ).fetchone()
        if lesson is None:
            raise TenantTaskNotFound("Lesson was not found.")
        if not isinstance(usage_id, str) or not usage_id.strip():
            raise ValueError("usage_id is required.")
        with self._connection:
            self._connection.execute(
                """INSERT INTO tenant_lesson_usage_events
                   (usage_id, tenant_id, task_id, attempt_id, lesson_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (usage_id, self._principal.tenant_id, task_id, attempt_id, lesson_id),
            )

    def list_lesson_uses(self, task_id: int) -> list:
        self._require_task(task_id, "lessons:read")
        rows = self._connection.execute(
            """SELECT * FROM tenant_lesson_usage_events
               WHERE tenant_id = ? AND task_id = ? ORDER BY recorded_at, usage_id""",
            (self._principal.tenant_id, task_id),
        ).fetchall()
        return [dict(row) for row in rows]
