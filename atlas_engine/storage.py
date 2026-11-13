import json
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
        active = conn.execute(
            "SELECT 1 FROM task_attempts WHERE task_id = ? AND state IN ('active', 'recovery_required') LIMIT 1",
            (task_id,),
        ).fetchone()
        if active is not None:
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
            lease_cursor = conn.execute(
                """
                UPDATE task_attempts
                SET state = ?, finished_at = ?
                WHERE task_id = ? AND attempt_id = ? AND worker_id = ?
                  AND fencing_token = ? AND state = 'active' AND lease_expires_at > ?
                """,
                (status, lease_now, task_id, attempt["attempt_id"],
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
