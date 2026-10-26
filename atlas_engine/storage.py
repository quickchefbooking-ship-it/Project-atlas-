import sqlite3
import os
from typing import Any, Dict, Optional

from .config import DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                success_criteria_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','running','passed','failed')),
                attempts INTEGER NOT NULL DEFAULT 0,
                score REAL NOT NULL DEFAULT 0.0,
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluations (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                passed INTEGER NOT NULL,
                score REAL NOT NULL,
                reasons_json TEXT NOT NULL,
                missing_requirements_json TEXT NOT NULL,
                method TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lessons (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                lesson_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                source TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                validated INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proposals (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                problem TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                proposed_change TEXT NOT NULL,
                expected_benefit TEXT NOT NULL,
                test_plan TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','tested')),
                created_by TEXT,
                approved_by TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def save_task(task_row: Dict[str, Any]) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO tasks (
                id, title, description, success_criteria_json, status, attempts, score, result_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_row["id"],
                task_row["title"],
                task_row["description"],
                task_row["success_criteria_json"],
                task_row["status"],
                task_row.get("attempts", 0),
                task_row.get("score", 0.0),
                task_row.get("result_json"),
                task_row["created_at"],
                task_row["updated_at"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


def list_tasks(limit: int = 50) -> list[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_task(task_id: str, updates: Dict[str, Any]) -> None:
    if not updates:
        return
    conn = get_connection()
    try:
        assignments = []
        params: list[Any] = []
        for key, value in updates.items():
            assignments.append(f"{key} = ?")
            params.append(value)
        params.append(task_id)
        conn.execute(
            f"UPDATE tasks SET {', '.join(assignments)} WHERE id = ?",
            tuple(params),
        )
        conn.commit()
    finally:
        conn.close()


def save_evaluation(record: Dict[str, Any]) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO evaluations (
                id, task_id, passed, score, reasons_json, missing_requirements_json, method, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["id"],
                record["task_id"],
                int(record["passed"]),
                record["score"],
                record["reasons_json"],
                record["missing_requirements_json"],
                record["method"],
                record["created_at"],
            ),
        )
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
        conn.execute(
            """
            INSERT INTO lessons (
                id, task_id, lesson_type, summary, source, evidence_json, validated, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["id"],
                record["task_id"],
                record["lesson_type"],
                record["summary"],
                record["source"],
                record["evidence_json"],
                int(record.get("validated", 0)),
                record["created_at"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_lessons(limit: int = 50) -> list[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM lessons ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def save_proposal(record: Dict[str, Any]) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO proposals (
                id, task_id, problem, evidence_json, proposed_change, expected_benefit, test_plan, status, created_by, approved_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["id"],
                record.get("task_id"),
                record["problem"],
                record["evidence_json"],
                record["proposed_change"],
                record["expected_benefit"],
                record["test_plan"],
                record["status"],
                record.get("created_by"),
                record.get("approved_by"),
                record["created_at"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_proposal(proposal_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


def list_proposals(limit: int = 50) -> list[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM proposals ORDER BY created_at DESC LIMIT ?",
            (limit,),
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
        "db_path": DB_PATH,
        "exists": exists,
        "persistent_storage": True,
        "tables": table_names,
    }


init_db()
