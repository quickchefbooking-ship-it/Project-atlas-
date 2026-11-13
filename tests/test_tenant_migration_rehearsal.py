"""Isolated rehearsal of the tenant backfill and composite-FK strategy.

This is deliberately a test-only miniature schema. It never imports the live
application storage module, reads ATLAS_DB_PATH, or changes production data.
"""
import sqlite3

import pytest


def _legacy_database(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL
        );
        CREATE TABLE task_attempts (
            attempt_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES tasks(id),
            state TEXT NOT NULL
        );
        CREATE TABLE evaluations (
            evaluation_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES tasks(id),
            score REAL NOT NULL
        );
        INSERT INTO tasks VALUES ('task-a', 'A'), ('task-b', 'B');
        INSERT INTO task_attempts VALUES
            ('attempt-a', 'task-a', 'completed'),
            ('attempt-b', 'task-b', 'failed');
        INSERT INTO evaluations VALUES
            ('eval-a', 'task-a', 1.0),
            ('eval-b', 'task-b', 0.0);
    """)
    conn.commit()
    return conn


def _rehearse_tenant_backfill(conn, task_owners):
    """Rebuild a disposable legacy DB using an explicit, complete owner map."""
    task_ids = {
        row[0] for row in conn.execute("SELECT id FROM tasks").fetchall()
    }
    if set(task_owners) != task_ids:
        raise ValueError("Every legacy task must have exactly one explicit tenant owner")
    if any(not isinstance(owner, str) or not owner.strip() for owner in task_owners.values()):
        raise ValueError("Tenant owner mapping must contain non-empty tenant IDs")

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute("""
            CREATE TABLE tenants (
                tenant_id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE memberships (
                tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
                subject TEXT NOT NULL,
                active INTEGER NOT NULL CHECK(active IN (0, 1)),
                PRIMARY KEY (tenant_id, subject)
            )
        """)
        owners = sorted(set(task_owners.values()))
        conn.executemany(
            "INSERT INTO tenants(tenant_id, name) VALUES (?, ?)",
            [(tenant_id, tenant_id) for tenant_id in owners],
        )
        conn.execute("""
            CREATE TABLE tasks_v2 (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
                title TEXT NOT NULL,
                UNIQUE (tenant_id, id)
            )
        """)
        conn.executemany(
            "INSERT INTO tasks_v2(id, tenant_id, title) VALUES (?, ?, ?)",
            [
                (task_id, task_owners[task_id], title)
                for task_id, title in conn.execute("SELECT id, title FROM tasks")
            ],
        )
        conn.execute("""
            CREATE TABLE task_attempts_v2 (
                attempt_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                state TEXT NOT NULL,
                FOREIGN KEY (tenant_id, task_id) REFERENCES tasks_v2(tenant_id, id)
            )
        """)
        conn.execute("""
            INSERT INTO task_attempts_v2
            SELECT a.attempt_id, t.tenant_id, a.task_id, a.state
            FROM task_attempts a JOIN tasks_v2 t ON t.id = a.task_id
        """)
        conn.execute("""
            CREATE TABLE evaluations_v2 (
                evaluation_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                score REAL NOT NULL,
                FOREIGN KEY (tenant_id, task_id) REFERENCES tasks_v2(tenant_id, id)
            )
        """)
        conn.execute("""
            INSERT INTO evaluations_v2
            SELECT e.evaluation_id, t.tenant_id, e.task_id, e.score
            FROM evaluations e JOIN tasks_v2 t ON t.id = e.task_id
        """)
        conn.execute("DROP TABLE evaluations")
        conn.execute("DROP TABLE task_attempts")
        conn.execute("DROP TABLE tasks")
        conn.execute("ALTER TABLE tasks_v2 RENAME TO tasks")
        conn.execute("ALTER TABLE task_attempts_v2 RENAME TO task_attempts")
        conn.execute("ALTER TABLE evaluations_v2 RENAME TO evaluations")
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValueError("Tenant migration rehearsal produced foreign-key violations")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def test_rehearsal_preserves_rows_and_assigns_explicit_tenant_ownership(tmp_path):
    conn = _legacy_database(tmp_path / "legacy.sqlite")
    try:
        _rehearse_tenant_backfill(
            conn, {"task-a": "tenant-one", "task-b": "tenant-two"}
        )
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM task_attempts").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0] == 2
        assert conn.execute(
            "SELECT tenant_id FROM tasks WHERE id='task-a'"
        ).fetchone()[0] == "tenant-one"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


@pytest.mark.parametrize("owners", [
    {"task-a": "tenant-one"},
    {"task-a": "tenant-one", "task-b": ""},
])
def test_rehearsal_fails_closed_on_missing_or_invalid_owner_mapping(tmp_path, owners):
    conn = _legacy_database(tmp_path / "legacy-invalid.sqlite")
    try:
        with pytest.raises(ValueError):
            _rehearse_tenant_backfill(conn, owners)
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 2
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tenants'"
        ).fetchone() is None
    finally:
        conn.close()


def test_composite_foreign_key_rejects_cross_tenant_child_relationship(tmp_path):
    conn = _legacy_database(tmp_path / "legacy-cross-tenant.sqlite")
    try:
        _rehearse_tenant_backfill(
            conn, {"task-a": "tenant-one", "task-b": "tenant-two"}
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO task_attempts
                   (attempt_id, tenant_id, task_id, state)
                   VALUES ('forged', 'tenant-two', 'task-a', 'active')"""
            )
    finally:
        conn.close()
