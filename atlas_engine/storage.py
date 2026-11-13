import sqlite3
import os
from datetime import datetime, timezone
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
            CREATE UNIQUE INDEX IF NOT EXISTS idx_source_documents_source_hash
            ON source_documents(source_id, content_sha256)
        """)
        conn.commit()
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
        conn.execute("""
            INSERT OR IGNORE INTO source_documents (
                id, source_id, title, uri, content, content_sha256, trust_level,
                state, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (record["id"], record["source_id"], record["title"], record["uri"],
              record["content"], record["content_sha256"], record["trust_level"],
              record["state"], record["metadata_json"], record["created_at"], record["updated_at"]))
        conn.commit()
        row = conn.execute(
            "SELECT * FROM source_documents WHERE source_id = ? AND content_sha256 = ?",
            (record["source_id"], record["content_sha256"]),
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


def list_source_documents(approved_only: bool = False, limit: int = 100) -> list[Dict[str, Any]]:
    conn = get_connection()
    try:
        if approved_only:
            rows = conn.execute(
                "SELECT * FROM source_documents WHERE state = 'approved' ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM source_documents ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def review_source_document(document_id: str, decision: str, reviewer: str, updated_at: str) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE source_documents SET state = ?, reviewed_by = ?, updated_at = ? WHERE id = ? AND state = 'pending'",
            (decision, reviewer, updated_at, document_id),
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
