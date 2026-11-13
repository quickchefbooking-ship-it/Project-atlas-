import json
import math
import sqlite3
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from .config import DB_PATH


def now_isoformat() -> str:
    """Return a timezone-aware UTC timestamp for persisted records."""
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    # SQLite does not enforce declared foreign keys unless enabled per connection.
    # Enable it here so every storage operation gets the same integrity guarantees.
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
                success_criteria_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','running','passed','failed')),
                attempts INTEGER NOT NULL DEFAULT 0, score REAL NOT NULL DEFAULT 0.0,
                result_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_attempts (
                attempt_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                fencing_token INTEGER NOT NULL,
                worker_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('active','recovery_required','completed','failed','abandoned')),
                claimed_at TEXT NOT NULL,
                heartbeat_at TEXT NOT NULL,
                lease_expires_at TEXT NOT NULL,
                finished_at TEXT,
                error_type TEXT,
                UNIQUE(task_id, attempt_number),
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_attempts_state_expiry
            ON task_attempts(state, lease_expires_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_attempts_task_history
            ON task_attempts(task_id, attempt_number DESC)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_recovery_decisions (
                decision_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('mark_failed','retry')),
                actor TEXT NOT NULL,
                reason TEXT NOT NULL,
                retry_safe INTEGER NOT NULL DEFAULT 0,
                side_effects_reconciled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id),
                FOREIGN KEY(attempt_id) REFERENCES task_attempts(attempt_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_recovery_decisions_task
            ON task_recovery_decisions(task_id, created_at DESC)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_cancellations (
                cancellation_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL UNIQUE,
                actor TEXT NOT NULL,
                reason TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('requested','acknowledged','too_late','requires_recovery')),
                requested_at TEXT NOT NULL,
                acknowledged_at TEXT,
                FOREIGN KEY(task_id) REFERENCES tasks(id),
                FOREIGN KEY(attempt_id) REFERENCES task_attempts(attempt_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_cancellations_task_state
            ON task_cancellations(task_id, state, requested_at DESC)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_retry_schedules (
                schedule_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                originating_attempt_id TEXT NOT NULL UNIQUE,
                next_attempt_number INTEGER NOT NULL,
                due_at TEXT NOT NULL,
                deadline_at TEXT NOT NULL,
                capability_name TEXT NOT NULL,
                capability_version TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                error_code TEXT NOT NULL,
                capability_contract_json TEXT NOT NULL DEFAULT '{}',
                policy_json TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('scheduled','claimed','cancelled','expired')),
                created_at TEXT NOT NULL,
                claimed_at TEXT,
                claimed_attempt_id TEXT,
                FOREIGN KEY(task_id) REFERENCES tasks(id),
                FOREIGN KEY(originating_attempt_id) REFERENCES task_attempts(attempt_id),
                FOREIGN KEY(claimed_attempt_id) REFERENCES task_attempts(attempt_id)
            )
        """)
        retry_schedule_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(task_retry_schedules)").fetchall()
        }
        if "capability_contract_json" not in retry_schedule_columns:
            conn.execute(
                "ALTER TABLE task_retry_schedules ADD COLUMN capability_contract_json TEXT NOT NULL DEFAULT '{}'"
            )
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_retry_schedules_due
            ON task_retry_schedules(state, due_at, deadline_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_retry_schedules_task
            ON task_retry_schedules(task_id, created_at DESC)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS evaluations (
                id TEXT PRIMARY KEY, task_id TEXT NOT NULL, passed INTEGER NOT NULL,
                score REAL NOT NULL, reasons_json TEXT NOT NULL,
                missing_requirements_json TEXT NOT NULL, method TEXT NOT NULL,
                created_at TEXT NOT NULL, FOREIGN KEY(task_id) REFERENCES tasks(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lessons (
                id TEXT PRIMARY KEY, task_id TEXT NOT NULL, lesson_type TEXT NOT NULL,
                summary TEXT NOT NULL, source TEXT NOT NULL, evidence_json TEXT NOT NULL,
                validated INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proposals (
                id TEXT PRIMARY KEY, task_id TEXT, problem TEXT NOT NULL,
                evidence_json TEXT NOT NULL, proposed_change TEXT NOT NULL,
                expected_benefit TEXT NOT NULL, test_plan TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','tested')),
                created_by TEXT, approved_by TEXT, created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, source_type TEXT NOT NULL,
                access_mode TEXT NOT NULL CHECK(access_mode IN ('read_only','draft_only','approval_gated')),
                enabled INTEGER NOT NULL DEFAULT 0, metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS source_documents (
                id TEXT PRIMARY KEY, source_id TEXT NOT NULL, title TEXT NOT NULL,
                uri TEXT NOT NULL, content TEXT NOT NULL, content_sha256 TEXT NOT NULL,
                trust_level TEXT NOT NULL CHECK(trust_level IN ('unverified','reviewed','authoritative')),
                state TEXT NOT NULL CHECK(state IN ('pending','approved','rejected')),
                reviewed_by TEXT, metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                FOREIGN KEY(source_id) REFERENCES sources(id)
            )
        """)
        # Additive migration for databases created before reviewer attribution existed.
        source_document_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(source_documents)").fetchall()
        }
        if "reviewed_by" not in source_document_columns:
            conn.execute("ALTER TABLE source_documents ADD COLUMN reviewed_by TEXT")
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_source_documents_source_hash_lookup
            ON source_documents(source_id, content_sha256)
        """)
        conn.commit()
    finally:
        conn.close()


def claim_task(task_id: str) -> bool:
    """Atomically claim a pending task so concurrent requests cannot run it twice."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            UPDATE tasks
            SET status = 'running', attempts = attempts + 1, updated_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (now_isoformat(), task_id),
        )
        conn.commit()
        return cursor.rowcount == 1
    finally:
        conn.close()


def _validate_lease_seconds(lease_seconds: int) -> int:
    if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int):
        raise ValueError("Lease duration must be an integer number of seconds.")
    if not 5 <= lease_seconds <= 3600:
        raise ValueError("Lease duration must be between 5 and 3600 seconds.")
    return lease_seconds


def _expire_retry_schedule_in_transaction(
    conn: sqlite3.Connection, schedule: sqlite3.Row, now_text: str,
) -> bool:
    """Expire one due retry and terminalise its pending task atomically."""
    cursor = conn.execute(
        "UPDATE task_retry_schedules SET state = 'expired' "
        "WHERE schedule_id = ? AND state = 'scheduled' AND deadline_at <= ?",
        (schedule["schedule_id"], now_text),
    )
    if cursor.rowcount != 1:
        return False
    task_cursor = conn.execute(
        """
        UPDATE tasks
        SET status = 'failed', score = 0.0, result_json = ?, updated_at = ?
        WHERE id = ? AND status = 'pending'
        """,
        (
            json.dumps({
                "error_type": "RetryDeadlineExpired",
                "schedule_id": schedule["schedule_id"],
            }, sort_keys=True),
            now_text,
            schedule["task_id"],
        ),
    )
    if task_cursor.rowcount == 1:
        conn.execute(
            """
            INSERT INTO evaluations (
                id, task_id, passed, score, reasons_json,
                missing_requirements_json, method, created_at
            ) VALUES (?, ?, 0, 0.0, ?, ?, 'retry_expired', ?)
            """,
            (
                f"evaluation-{os.urandom(12).hex()}",
                schedule["task_id"],
                json.dumps(["The scheduled retry deadline elapsed before another attempt was claimed."]),
                json.dumps(["A new attempt requires a fresh, explicitly reviewed task."]),
                now_text,
            ),
        )
    return True


def claim_task_with_lease(task_id: str, worker_id: str, lease_seconds: int = 60) -> Optional[Dict[str, Any]]:
    """Atomically claim a pending task and create its fenced worker lease.

    An expired/recovery-required attempt is never reclaimed automatically.
    """
    _validate_lease_seconds(lease_seconds)
    if not isinstance(worker_id, str) or not worker_id.strip() or len(worker_id) > 128:
        raise ValueError("A non-empty worker ID of at most 128 characters is required.")
    now = datetime.now(timezone.utc)
    claimed_at = now.isoformat()
    expires_at = (now + timedelta(seconds=lease_seconds)).isoformat()
    attempt_id = f"attempt-{os.urandom(12).hex()}"
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        task = conn.execute(
            "SELECT attempts, status FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if task is None or task["status"] != "pending":
            conn.rollback()
            return None
        cancelled = conn.execute(
            "SELECT 1 FROM task_cancellations WHERE task_id = ? AND state = 'acknowledged' LIMIT 1",
            (task_id,),
        ).fetchone()
        if cancelled is not None:
            conn.rollback()
            return None
        active = conn.execute(
            "SELECT 1 FROM task_attempts WHERE task_id = ? AND state IN ('active', 'recovery_required') LIMIT 1",
            (task_id,),
        ).fetchone()
        if active is not None:
            conn.rollback()
            return None
        schedule = conn.execute(
            """
            SELECT * FROM task_retry_schedules
            WHERE task_id = ?
            ORDER BY created_at DESC, rowid DESC LIMIT 1
            """,
            (task_id,),
        ).fetchone()
        if schedule is not None:
            if schedule["state"] != "scheduled":
                conn.rollback()
                return None
            if schedule["deadline_at"] <= claimed_at:
                _expire_retry_schedule_in_transaction(conn, schedule, claimed_at)
                conn.commit()
                return None
            if schedule["due_at"] > claimed_at or int(schedule["next_attempt_number"]) != int(task["attempts"]) + 1:
                conn.rollback()
                return None
        attempt_number = int(task["attempts"]) + 1
        fencing_token = conn.execute(
            "SELECT COALESCE(MAX(fencing_token), 0) + 1 FROM task_attempts WHERE task_id = ?",
            (task_id,),
        ).fetchone()[0]
        updated = conn.execute(
            "UPDATE tasks SET status = 'running', attempts = ?, updated_at = ? "
            "WHERE id = ? AND status = 'pending'",
            (attempt_number, claimed_at, task_id),
        )
        if updated.rowcount != 1:
            conn.rollback()
            return None
        conn.execute(
            """
            INSERT INTO task_attempts (
                attempt_id, task_id, attempt_number, fencing_token, worker_id,
                state, claimed_at, heartbeat_at, lease_expires_at
            ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (attempt_id, task_id, attempt_number, fencing_token, worker_id,
             claimed_at, claimed_at, expires_at),
        )
        if schedule is not None:
            scheduled = conn.execute(
                """
                UPDATE task_retry_schedules
                SET state = 'claimed', claimed_at = ?, claimed_attempt_id = ?
                WHERE schedule_id = ? AND state = 'scheduled' AND due_at <= ? AND deadline_at > ?
                """,
                (claimed_at, attempt_id, schedule["schedule_id"], claimed_at, claimed_at),
            )
            if scheduled.rowcount != 1:
                conn.rollback()
                return None
        conn.commit()
        return {
            "attempt_id": attempt_id, "task_id": task_id,
            "attempt_number": attempt_number, "fencing_token": fencing_token,
            "worker_id": worker_id, "state": "active",
            "claimed_at": claimed_at, "heartbeat_at": claimed_at,
            "lease_expires_at": expires_at,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def heartbeat_task_attempt(
    task_id: str, attempt_id: str, worker_id: str, fencing_token: int,
    lease_seconds: int = 60,
) -> bool:
    """Extend only the matching, still-live lease; expired leases need recovery."""
    _validate_lease_seconds(lease_seconds)
    now = datetime.now(timezone.utc)
    now_text = now.isoformat()
    expires_at = (now + timedelta(seconds=lease_seconds)).isoformat()
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            UPDATE task_attempts
            SET heartbeat_at = ?, lease_expires_at = ?
            WHERE task_id = ? AND attempt_id = ? AND worker_id = ?
              AND fencing_token = ? AND state = 'active' AND lease_expires_at > ?
            """,
            (now_text, expires_at, task_id, attempt_id, worker_id,
             fencing_token, now_text),
        )
        conn.commit()
        return cursor.rowcount == 1
    finally:
        conn.close()


def mark_expired_task_attempts(now: Optional[str] = None, limit: int = 100) -> int:
    """Mark stale leases for operator recovery; never requeue or rerun their tasks."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("Expiry scan limit must be between 1 and 500.")
    now_text = now or now_isoformat()
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """
            SELECT attempt_id FROM task_attempts
            WHERE state = 'active' AND lease_expires_at <= ?
            ORDER BY lease_expires_at ASC LIMIT ?
            """,
            (now_text, limit),
        ).fetchall()
        ids = [row["attempt_id"] for row in rows]
        if ids:
            conn.executemany(
                "UPDATE task_attempts SET state = 'recovery_required' "
                "WHERE attempt_id = ? AND state = 'active' AND lease_expires_at <= ?",
                [(attempt_id, now_text) for attempt_id in ids],
            )
            conn.executemany(
                """
                UPDATE task_cancellations
                SET state = 'requires_recovery'
                WHERE attempt_id = ? AND state = 'requested'
                """,
                [(attempt_id,) for attempt_id in ids],
            )
        conn.commit()
        return len(ids)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_recovery_required_attempts(limit: int = 100) -> list[Dict[str, Any]]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("Recovery list limit must be between 1 and 500.")
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT a.*, t.title AS task_title, t.status AS task_status
            FROM task_attempts a JOIN tasks t ON t.id = a.task_id
            WHERE a.state = 'recovery_required'
            ORDER BY a.lease_expires_at ASC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_task_attempts(task_id: str) -> list[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM task_attempts WHERE task_id = ? ORDER BY attempt_number ASC",
            (task_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def resolve_task_recovery(
    task_id: str, attempt_id: str, action: str, actor: str, reason: str,
    retry_safe: bool = False, side_effects_reconciled: bool = False,
) -> bool:
    """Record an explicit recovery decision; retry only after safety is attested."""
    if action not in {"mark_failed", "retry"}:
        raise ValueError("Recovery action must be mark_failed or retry.")
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 128:
        raise ValueError("Recovery actor must contain 1 to 128 characters.")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
        raise ValueError("Recovery reason must contain 1 to 500 characters.")
    if action == "retry" and not (retry_safe is True and side_effects_reconciled is True):
        raise ValueError("Retry requires explicit confirmation that replay is safe and side effects are reconciled.")
    now = now_isoformat()
    decision_id = f"recovery-{os.urandom(12).hex()}"
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        attempt = conn.execute(
            "SELECT * FROM task_attempts WHERE task_id = ? AND attempt_id = ?",
            (task_id, attempt_id),
        ).fetchone()
        task = conn.execute(
            "SELECT status FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if attempt is None or attempt["state"] != "recovery_required" or task is None or task["status"] != "running":
            conn.rollback()
            return False

        if action == "mark_failed":
            cursor = conn.execute(
                """
                UPDATE tasks
                SET status = 'failed', score = 0.0,
                    result_json = ?, updated_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (json.dumps({"error_type": "WorkerInterrupted"}, sort_keys=True), now, task_id),
            )
            if cursor.rowcount != 1:
                conn.rollback()
                return False
            conn.execute(
                """
                INSERT INTO evaluations (
                    id, task_id, passed, score, reasons_json,
                    missing_requirements_json, method, created_at
                ) VALUES (?, ?, 0, 0.0, ?, ?, ?, ?)
                """,
                (
                    f"evaluation-{os.urandom(12).hex()}", task_id,
                    json.dumps(["Worker lease expired; operator marked the interrupted attempt failed."]),
                    json.dumps(["Task execution completed with a verified outcome."]),
                    "recovery_operator_decision", now,
                ),
            )
            attempt_state = "failed"
            error_type = "WorkerInterrupted"
        else:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET status = 'pending', score = 0.0, result_json = NULL, updated_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (now, task_id),
            )
            if cursor.rowcount != 1:
                conn.rollback()
                return False
            attempt_state = "abandoned"
            error_type = "RetryExplicitlyApproved"

        attempt_cursor = conn.execute(
            """
            UPDATE task_attempts
            SET state = ?, finished_at = ?, error_type = ?
            WHERE task_id = ? AND attempt_id = ? AND state = 'recovery_required'
            """,
            (attempt_state, now, error_type, task_id, attempt_id),
        )
        if attempt_cursor.rowcount != 1:
            conn.rollback()
            return False
        conn.execute(
            """
            INSERT INTO task_recovery_decisions (
                decision_id, task_id, attempt_id, action, actor, reason,
                retry_safe, side_effects_reconciled, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id, task_id, attempt_id, action, actor.strip(), reason.strip(),
                int(retry_safe is True), int(side_effects_reconciled is True), now,
            ),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_task_recovery_decisions(task_id: str) -> list[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM task_recovery_decisions WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()




def save_task(task_row: Dict[str, Any]) -> None:
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO tasks (
                id, title, description, success_criteria_json, status, attempts,
                score, result_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_row["id"], task_row["title"], task_row["description"],
            task_row["success_criteria_json"], task_row["status"],
            task_row.get("attempts", 0), task_row.get("score", 0.0),
            task_row.get("result_json"), task_row["created_at"], task_row["updated_at"],
        ))
        conn.commit()
    finally:
        conn.close()


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def list_tasks(limit: int = 50) -> list[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_task(task_id: str, updates: Dict[str, Any]) -> None:
    if not updates:
        return
    allowed_columns = {
        "title", "description", "success_criteria_json", "status",
        "attempts", "score", "result_json", "updated_at",
    }
    unknown_columns = set(updates) - allowed_columns
    if unknown_columns:
        raise ValueError(f"Unsupported task update fields: {', '.join(sorted(unknown_columns))}")
    conn = get_connection()
    try:
        assignments = [f"{key} = ?" for key in updates]
        params = list(updates.values()) + [task_id]
        conn.execute(
            f"UPDATE tasks SET {', '.join(assignments)} WHERE id = ?", tuple(params)
        )
        conn.commit()
    finally:
        conn.close()


def save_evaluation(record: Dict[str, Any]) -> None:
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO evaluations (
                id, task_id, passed, score, reasons_json,
                missing_requirements_json, method, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record["id"], record["task_id"], int(record["passed"]),
            record["score"], record["reasons_json"],
            record["missing_requirements_json"], record["method"], record["created_at"],
        ))
        conn.commit()
    finally:
        conn.close()


def complete_task_with_evaluation(
    task_id: str,
    record: Dict[str, Any],
    status: str,
    result: Dict[str, Any],
    attempt: Optional[Dict[str, Any]] = None,
) -> bool:
    """Persist a task's terminal state and evaluation as one SQLite transaction.

    Only a currently running task can be completed. If either write fails, both
    writes roll back so the task cannot appear complete without its evaluation.
    """
    if status not in {"passed", "failed"}:
        raise ValueError("Task completion status must be passed or failed.")
    if record.get("task_id") != task_id:
        raise ValueError("Evaluation task ID does not match the task being completed.")
    expected_status = "passed" if bool(record.get("passed")) else "failed"
    if status != expected_status:
        raise ValueError("Task status does not match the evaluation outcome.")

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if attempt is not None:
            lease_now = now_isoformat()
            cancellation = conn.execute(
                "SELECT state FROM task_cancellations WHERE task_id = ? AND attempt_id = ?",
                (task_id, attempt["attempt_id"]),
            ).fetchone()
            if cancellation is not None and cancellation["state"] == "requested":
                conn.rollback()
                return False
            attempt_state = "completed" if status == "passed" else "failed"
            lease_cursor = conn.execute(
                """
                UPDATE task_attempts
                SET state = ?, finished_at = ?
                WHERE task_id = ? AND attempt_id = ? AND worker_id = ?
                  AND fencing_token = ? AND state = 'active' AND lease_expires_at > ?
                """,
                (attempt_state, lease_now, task_id, attempt["attempt_id"],
                 attempt["worker_id"], attempt["fencing_token"], lease_now),
            )
            if lease_cursor.rowcount != 1:
                conn.rollback()
                return False
        cursor = conn.execute(
            """
            UPDATE tasks
            SET status = ?, score = ?, result_json = ?, updated_at = ?
            WHERE id = ? AND status = 'running'
            """,
            (
                status,
                record["score"],
                json.dumps(result, sort_keys=True),
                record["created_at"],
                task_id,
            ),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return False

        conn.execute(
            """
            INSERT INTO evaluations (
                id, task_id, passed, score, reasons_json,
                missing_requirements_json, method, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["id"], record["task_id"], int(record["passed"]),
                record["score"], record["reasons_json"],
                record["missing_requirements_json"], record["method"], record["created_at"],
            ),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _normalise_utc_timestamp(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone.")
    return parsed.astimezone(timezone.utc).isoformat()


def persist_task_retry_schedule(
    task_id: str,
    attempt: Dict[str, Any],
    evaluation_record: Dict[str, Any],
    *,
    capability_contract: Dict[str, Any],
    policy_snapshot: Dict[str, Any],
    error_code: str,
    idempotency_key: str,
    due_at: str,
    deadline_at: str,
) -> Optional[Dict[str, Any]]:
    """Atomically finish an attempt and persist a bounded, capability-verified retry.

    This is an internal engine primitive, not an API endpoint. Existing executors
    do not call it; a trusted capability registry must be introduced before any
    unattended retry can be enabled.
    """
    if not isinstance(capability_contract, dict):
        raise ValueError("A trusted capability contract is required.")
    name = capability_contract.get("capability_name")
    version = capability_contract.get("version")
    allowed_codes = capability_contract.get("retryable_error_codes")
    if not isinstance(name, str) or not name.strip() or not isinstance(version, str) or not version.strip():
        raise ValueError("Capability name and version are required.")
    if capability_contract.get("idempotent") is not True:
        raise ValueError("Capability must declare idempotency.")
    if capability_contract.get("side_effects_declared") is not True:
        raise ValueError("Capability side effects must be declared.")
    if capability_contract.get("duplicate_suppression_verified") is not True:
        raise ValueError("Duplicate suppression must be verified.")
    if not isinstance(error_code, str) or not error_code.strip():
        raise ValueError("A non-empty retryable error code is required.")
    if not isinstance(allowed_codes, (list, tuple, set, frozenset)) or error_code not in allowed_codes:
        raise ValueError("The transient error code is not allowlisted by the capability.")
    verification_evidence = capability_contract.get("verification_evidence")
    if not isinstance(verification_evidence, str) or not verification_evidence.strip() or len(verification_evidence) > 512:
        raise ValueError("A verifiable capability test-evidence reference is required.")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 256:
        raise ValueError("A stable idempotency key of at most 256 characters is required.")
    if not isinstance(policy_snapshot, dict):
        raise ValueError("An immutable retry policy snapshot is required.")
    max_attempts = policy_snapshot.get("max_attempts")
    attempt_timeout = policy_snapshot.get("per_attempt_timeout_seconds")
    total_deadline = policy_snapshot.get("total_deadline_seconds")
    base_delay = policy_snapshot.get("base_delay_seconds")
    max_delay = policy_snapshot.get("max_delay_seconds")
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 2 <= max_attempts <= 3:
        raise ValueError("Retry policy must permit between 2 and 3 total attempts.")
    if isinstance(attempt_timeout, bool) or not isinstance(attempt_timeout, int) or not 1 <= attempt_timeout <= 30:
        raise ValueError("Per-attempt timeout must be between 1 and 30 seconds.")
    if isinstance(total_deadline, bool) or not isinstance(total_deadline, int) or not 1 <= total_deadline <= 90:
        raise ValueError("Total retry deadline must be between 1 and 90 seconds.")
    for field_name, value in (("base_delay_seconds", base_delay), ("max_delay_seconds", max_delay)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 15:
            raise ValueError(f"{field_name} must be finite, greater than 0 and at most 15 seconds.")
    if base_delay > max_delay:
        raise ValueError("Base retry delay cannot exceed maximum retry delay.")
    due_text = _normalise_utc_timestamp(due_at, "due_at")
    deadline_text = _normalise_utc_timestamp(deadline_at, "deadline_at")
    now = datetime.now(timezone.utc)
    due_dt = datetime.fromisoformat(due_text)
    deadline_dt = datetime.fromisoformat(deadline_text)
    if due_dt <= now or deadline_dt <= due_dt:
        raise ValueError("Retry due time must be in the future and before its deadline.")
    if deadline_dt > now + timedelta(seconds=total_deadline):
        raise ValueError("Retry deadline cannot exceed the policy's total task deadline.")
    if evaluation_record.get("task_id") != task_id or evaluation_record.get("passed") is not False:
        raise ValueError("Retry scheduling requires a failed evaluation for this task.")
    required_eval = {"id", "score", "reasons_json", "missing_requirements_json", "method"}
    if not required_eval.issubset(evaluation_record):
        raise ValueError("Retry evaluation record is incomplete.")

    now_text = now.isoformat()
    schedule_id = f"retry-{os.urandom(12).hex()}"
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            """
            SELECT a.*, t.status AS task_status
            FROM task_attempts a JOIN tasks t ON t.id = a.task_id
            WHERE a.task_id = ? AND a.attempt_id = ? AND a.worker_id = ?
              AND a.fencing_token = ? AND a.state = 'active'
              AND a.lease_expires_at > ?
            """,
            (task_id, attempt["attempt_id"], attempt["worker_id"],
             attempt["fencing_token"], now_text),
        ).fetchone()
        if current is None or current["task_status"] != "running":
            conn.rollback()
            return None
        cancellation = conn.execute(
            """
            SELECT 1 FROM task_cancellations
            WHERE task_id = ? AND attempt_id = ? AND state = 'requested'
            """,
            (task_id, attempt["attempt_id"]),
        ).fetchone()
        if cancellation is not None:
            conn.rollback()
            return None
        outstanding = conn.execute(
            "SELECT 1 FROM task_retry_schedules WHERE task_id = ? AND state = 'scheduled' LIMIT 1",
            (task_id,),
        ).fetchone()
        if outstanding is not None:
            conn.rollback()
            return None
        next_attempt_number = int(current["attempt_number"]) + 1
        if next_attempt_number > max_attempts:
            conn.rollback()
            return None

        attempt_cursor = conn.execute(
            """
            UPDATE task_attempts
            SET state = 'failed', finished_at = ?, error_type = ?
            WHERE task_id = ? AND attempt_id = ? AND worker_id = ?
              AND fencing_token = ? AND state = 'active' AND lease_expires_at > ?
            """,
            (now_text, f"RetryScheduled:{error_code}", task_id,
             attempt["attempt_id"], attempt["worker_id"], attempt["fencing_token"], now_text),
        )
        if attempt_cursor.rowcount != 1:
            conn.rollback()
            return None
        task_cursor = conn.execute(
            """
            UPDATE tasks
            SET status = 'pending', score = 0.0, result_json = ?, updated_at = ?
            WHERE id = ? AND status = 'running'
            """,
            (json.dumps({"retry_scheduled": True, "error_code": error_code}, sort_keys=True),
             now_text, task_id),
        )
        if task_cursor.rowcount != 1:
            conn.rollback()
            return None
        conn.execute(
            """
            INSERT INTO evaluations (
                id, task_id, passed, score, reasons_json,
                missing_requirements_json, method, created_at
            ) VALUES (?, ?, 0, ?, ?, ?, ?, ?)
            """,
            (
                evaluation_record["id"], task_id, evaluation_record["score"],
                evaluation_record["reasons_json"], evaluation_record["missing_requirements_json"],
                evaluation_record["method"], now_text,
            ),
        )
        conn.execute(
            """
            INSERT INTO task_retry_schedules (
                schedule_id, task_id, originating_attempt_id, next_attempt_number,
                due_at, deadline_at, capability_name, capability_version,
                idempotency_key, error_code, capability_contract_json, policy_json, state, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled', ?)
            """,
            (
                schedule_id, task_id, attempt["attempt_id"], next_attempt_number,
                due_text, deadline_text, name.strip(), version.strip(),
                idempotency_key.strip(), error_code,
                json.dumps(capability_contract, sort_keys=True),
                json.dumps(policy_snapshot, sort_keys=True), now_text,
            ),
        )
        conn.commit()
        return {
            "schedule_id": schedule_id,
            "task_id": task_id,
            "originating_attempt_id": attempt["attempt_id"],
            "next_attempt_number": next_attempt_number,
            "due_at": due_text,
            "deadline_at": deadline_text,
            "state": "scheduled",
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def expire_task_retry_schedules(now: Optional[str] = None, limit: int = 100) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("Retry schedule expiry limit must be between 1 and 500.")
    now_text = _normalise_utc_timestamp(now or now_isoformat(), "now")
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """
            SELECT * FROM task_retry_schedules
            WHERE state = 'scheduled' AND deadline_at <= ?
            ORDER BY deadline_at ASC LIMIT ?
            """,
            (now_text, limit),
        ).fetchall()
        expired_count = sum(
            1 for row in rows
            if _expire_retry_schedule_in_transaction(conn, row, now_text)
        )
        conn.commit()
        return expired_count
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_due_task_retry_schedules(now: Optional[str] = None, limit: int = 50) -> list[Dict[str, Any]]:
    """Read-only scheduler scan; never claims or executes due work."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Due retry scan limit must be between 1 and 100.")
    now_text = _normalise_utc_timestamp(now or now_isoformat(), "now")
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT r.*, t.title AS task_title, t.status AS task_status, t.attempts AS task_attempts
            FROM task_retry_schedules r
            JOIN tasks t ON t.id = r.task_id
            WHERE r.state = 'scheduled' AND r.due_at <= ?
              AND r.deadline_at > ? AND t.status = 'pending'
            ORDER BY r.due_at ASC, r.created_at ASC LIMIT ?
            """,
            (now_text, now_text, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_task_retry_schedules(task_id: str) -> list[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM task_retry_schedules WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def request_task_cancellation(
    task_id: str, attempt_id: str, actor: str, reason: str,
) -> Optional[Dict[str, Any]]:
    """Persist an idempotent cancellation request for the currently leased attempt."""
    if not isinstance(actor, str) or not actor.strip() or len(actor.strip()) > 128:
        raise ValueError("Cancellation actor must contain 1 to 128 characters.")
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 500:
        raise ValueError("Cancellation reason must contain 1 to 500 characters.")
    now = now_isoformat()
    cancellation_id = f"cancel-{os.urandom(12).hex()}"
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM task_cancellations WHERE task_id = ? AND attempt_id = ?",
            (task_id, attempt_id),
        ).fetchone()
        if existing is not None:
            conn.commit()
            return dict(existing)
        attempt_row = conn.execute(
            "SELECT state, lease_expires_at FROM task_attempts WHERE task_id = ? AND attempt_id = ?",
            (task_id, attempt_id),
        ).fetchone()
        task = conn.execute(
            "SELECT status FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if attempt_row is None or task is None:
            conn.rollback()
            return None
        if task["status"] == "pending" and attempt_row["state"] == "failed":
            scheduled_retry = conn.execute(
                """
                SELECT * FROM task_retry_schedules
                WHERE task_id = ? AND originating_attempt_id = ? AND state = 'scheduled'
                """,
                (task_id, attempt_id),
            ).fetchone()
            if scheduled_retry is not None:
                schedule_cursor = conn.execute(
                    "UPDATE task_retry_schedules SET state = 'cancelled' "
                    "WHERE schedule_id = ? AND state = 'scheduled'",
                    (scheduled_retry["schedule_id"],),
                )
                task_cursor = conn.execute(
                    """
                    UPDATE tasks
                    SET status = 'failed', score = 0.0, result_json = ?, updated_at = ?
                    WHERE id = ? AND status = 'pending'
                    """,
                    (
                        json.dumps({
                            "error_type": "TaskCancelled",
                            "cancelled_before_retry": True,
                            "schedule_id": scheduled_retry["schedule_id"],
                        }, sort_keys=True),
                        now,
                        task_id,
                    ),
                )
                if schedule_cursor.rowcount != 1 or task_cursor.rowcount != 1:
                    conn.rollback()
                    return None
                conn.execute(
                    """
                    INSERT INTO evaluations (
                        id, task_id, passed, score, reasons_json,
                        missing_requirements_json, method, created_at
                    ) VALUES (?, ?, 0, 0.0, ?, ?, 'cancelled', ?)
                    """,
                    (
                        f"evaluation-{os.urandom(12).hex()}",
                        task_id,
                        json.dumps(["A scheduled retry was cancelled before another attempt began."]),
                        json.dumps(["The task was cancelled before retry execution."]),
                        now,
                    ),
                )
                cancellation_state = "acknowledged"
            else:
                cancellation_state = "too_late"
        elif task["status"] != "running" or attempt_row["state"] in {"completed", "failed", "abandoned"}:
            cancellation_state = "too_late"
        elif attempt_row["state"] == "recovery_required" or attempt_row["lease_expires_at"] <= now:
            cancellation_state = "requires_recovery"
        elif attempt_row["state"] == "active":
            cancellation_state = "requested"
        else:
            conn.rollback()
            return None
        conn.execute(
            """
            INSERT INTO task_cancellations (
                cancellation_id, task_id, attempt_id, actor, reason,
                state, requested_at, acknowledged_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (cancellation_id, task_id, attempt_id, actor.strip(), reason.strip(),
             cancellation_state, now, now if cancellation_state == "acknowledged" else None),
        )
        row = conn.execute(
            "SELECT * FROM task_cancellations WHERE cancellation_id = ?",
            (cancellation_id,),
        ).fetchone()
        conn.commit()
        return dict(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_task_cancellation(
    task_id: str, attempt_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        if attempt_id is None:
            row = conn.execute(
                "SELECT * FROM task_cancellations WHERE task_id = ? ORDER BY requested_at DESC LIMIT 1",
                (task_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM task_cancellations WHERE task_id = ? AND attempt_id = ?",
                (task_id, attempt_id),
            ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def acknowledge_task_cancellation(
    task_id: str, attempt: Dict[str, Any], record: Dict[str, Any],
) -> bool:
    """Atomically acknowledge cancellation and persist task/evaluation/attempt outcome."""
    if record.get("task_id") != task_id or record.get("method") != "cancelled":
        raise ValueError("Cancellation evaluation record is invalid.")
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        now = now_isoformat()
        cancellation = conn.execute(
            """
            SELECT * FROM task_cancellations
            WHERE task_id = ? AND attempt_id = ? AND state = 'requested'
            """,
            (task_id, attempt["attempt_id"]),
        ).fetchone()
        if cancellation is None:
            conn.rollback()
            return False
        lease_cursor = conn.execute(
            """
            UPDATE task_attempts
            SET state = 'failed', finished_at = ?, error_type = 'TaskCancelled'
            WHERE task_id = ? AND attempt_id = ? AND worker_id = ?
              AND fencing_token = ? AND state = 'active' AND lease_expires_at > ?
            """,
            (now, task_id, attempt["attempt_id"], attempt["worker_id"],
             attempt["fencing_token"], now),
        )
        if lease_cursor.rowcount != 1:
            conn.rollback()
            return False
        task_cursor = conn.execute(
            """
            UPDATE tasks
            SET status = 'failed', score = 0.0, result_json = ?, updated_at = ?
            WHERE id = ? AND status = 'running'
            """,
            (json.dumps({"error_type": "TaskCancelled"}, sort_keys=True), now, task_id),
        )
        if task_cursor.rowcount != 1:
            conn.rollback()
            return False
        conn.execute(
            """
            INSERT INTO evaluations (
                id, task_id, passed, score, reasons_json,
                missing_requirements_json, method, created_at
            ) VALUES (?, ?, 0, 0.0, ?, ?, 'cancelled', ?)
            """,
            (
                record["id"], task_id,
                json.dumps(["Cancellation request acknowledged at a cooperative safe point."]),
                json.dumps(["Task execution was cancelled before its outcome was committed."]),
                now,
            ),
        )
        cancel_cursor = conn.execute(
            """
            UPDATE task_cancellations
            SET state = 'acknowledged', acknowledged_at = ?
            WHERE cancellation_id = ? AND state = 'requested'
            """,
            (now, cancellation["cancellation_id"]),
        )
        if cancel_cursor.rowcount != 1:
            conn.rollback()
            return False
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_evaluations_for_task(task_id: str) -> list[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM evaluations WHERE task_id = ? ORDER BY created_at DESC",
            (task_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def save_lesson(record: Dict[str, Any]) -> None:
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO lessons (
                id, task_id, lesson_type, summary, source, evidence_json, validated, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record["id"], record["task_id"], record["lesson_type"], record["summary"],
            record["source"], record["evidence_json"], int(record.get("validated", 0)),
            record["created_at"],
        ))
        conn.commit()
    finally:
        conn.close()


def list_lessons(limit: int = 50, validated_only: bool = False) -> list[Dict[str, Any]]:
    conn = get_connection()
    try:
        if validated_only:
            rows = conn.execute(
                "SELECT * FROM lessons WHERE validated = 1 ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM lessons ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def search_validated_lessons(keywords: list[str], limit: int = 5) -> list[Dict[str, Any]]:
    """Return exact-token matches ranked across all validated lessons."""
    if not isinstance(limit, int) or limit < 1 or limit > 50:
        raise ValueError("Lesson retrieval limit must be between 1 and 50.")
    if not isinstance(keywords, list):
        raise ValueError("Lesson keywords must be a list.")

    safe_keywords = sorted({
        word.lower() for word in keywords
        if isinstance(word, str) and word and all(char.isalnum() or char == "_" for char in word)
    })[:64]
    if not safe_keywords:
        return []

    patterns = ["*[^a-z0-9_]" + word + "[^a-z0-9_]*" for word in safe_keywords]
    match_expression = " OR ".join(
        "lower(' ' || summary || ' ' || source || ' ') GLOB ?" for _ in patterns
    )
    score_expression = " + ".join(
        "CASE WHEN lower(' ' || summary || ' ' || source || ' ') GLOB ? THEN 1 ELSE 0 END"
        for _ in patterns
    )
    columns = "id, task_id, lesson_type, summary, source, evidence_json, validated, created_at"
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT " + columns + " FROM lessons WHERE validated = 1 AND (" + match_expression + ") "
            "ORDER BY (" + score_expression + ") DESC, created_at DESC, id DESC LIMIT ?",
            tuple(patterns + patterns + [limit]),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def save_proposal(record: Dict[str, Any]) -> None:
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO proposals (
                id, task_id, problem, evidence_json, proposed_change, expected_benefit,
                test_plan, status, created_by, approved_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record["id"], record.get("task_id"), record["problem"], record["evidence_json"],
            record["proposed_change"], record["expected_benefit"], record["test_plan"],
            record["status"], record.get("created_by"), record.get("approved_by"),
            record["created_at"],
        ))
        conn.commit()
    finally:
        conn.close()


def get_proposal(proposal_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def list_proposals(limit: int = 50) -> list[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM proposals ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_proposal_status(proposal_id: str, status: str, approved_by: Optional[str] = None) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE proposals SET status = ?, approved_by = ? WHERE id = ?",
            (status, approved_by, proposal_id),
        )
        conn.commit()
    finally:
        conn.close()


def save_source(record: Dict[str, Any]) -> None:
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO sources (id, name, source_type, access_mode, enabled, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, source_type=excluded.source_type,
                access_mode=excluded.access_mode, enabled=excluded.enabled,
                metadata_json=excluded.metadata_json, updated_at=excluded.updated_at
        """, (record["id"], record["name"], record["source_type"], record["access_mode"],
              int(record.get("enabled", False)), record["metadata_json"],
              record["created_at"], record["updated_at"]))
        conn.commit()
    finally:
        conn.close()


def get_source(source_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def list_sources() -> list[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM sources ORDER BY name COLLATE NOCASE").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def save_source_document(record: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_connection()
    try:
        # Serialize the check-and-insert so concurrent imports cannot create
        # duplicate source/content pairs. A non-unique index keeps old databases
        # with pre-existing duplicates migratable without deleting user data.
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM source_documents WHERE source_id = ? AND content_sha256 = ? "
            "ORDER BY created_at, id LIMIT 1",
            (record["source_id"], record["content_sha256"]),
        ).fetchone()
        if existing is not None:
            conn.commit()
            return dict(existing)
        conn.execute("""
            INSERT INTO source_documents (
                id, source_id, title, uri, content, content_sha256, trust_level,
                state, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (record["id"], record["source_id"], record["title"], record["uri"],
              record["content"], record["content_sha256"], record["trust_level"],
              record["state"], record["metadata_json"], record["created_at"], record["updated_at"]))
        conn.commit()
        row = conn.execute(
            "SELECT * FROM source_documents WHERE id = ?", (record["id"],)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_source_document(document_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM source_documents WHERE id = ?", (document_id,)).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def get_source_document_by_hash(source_id: str, content_sha256: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM source_documents WHERE source_id = ? AND content_sha256 = ? "
            "ORDER BY created_at, id LIMIT 1",
            (source_id, content_sha256),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def list_source_documents(
    approved_only: bool = False, limit: int = 100, state: Optional[str] = None
) -> list[Dict[str, Any]]:
    """List bounded source records, optionally filtered to one review state."""
    if state is not None and state not in {"pending", "approved", "rejected"}:
        raise ValueError("Unsupported source document state.")
    if not isinstance(limit, int) or limit < 1 or limit > 500:
        raise ValueError("Limit must be between 1 and 500.")
    conn = get_connection()
    try:
        clauses = []
        params: list[Any] = []
        if approved_only:
            clauses.append("state = 'approved'")
        if state is not None:
            clauses.append("state = ?")
            params.append(state)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)
        rows = conn.execute(
            f"SELECT * FROM source_documents{where} ORDER BY updated_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def review_source_document(document_id: str, decision: str, reviewer: str, updated_at: str) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            UPDATE source_documents
            SET state = ?,
                trust_level = CASE WHEN ? = 'approved' THEN 'reviewed' ELSE trust_level END,
                reviewed_by = ?,
                updated_at = ?
            WHERE id = ? AND state = 'pending'
            """,
            (decision, decision, reviewer, updated_at, document_id),
        )
        conn.commit()
        return cursor.rowcount == 1
    finally:
        conn.close()


def get_database_status() -> Dict[str, Any]:
    exists = os.path.exists(DB_PATH)
    connection = get_connection()
    try:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [row[0] for row in tables]
    finally:
        connection.close()
    return {
        "db_path": DB_PATH, "exists": exists, "persistent_storage": True,
        "tables": table_names,
    }


init_db()
