import sqlite3

import pytest

from atlas_engine.sqlite_transaction import atomic_transaction


def make_db():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE values_seen (value INTEGER PRIMARY KEY)")
    return db


def test_nested_savepoint_rolls_back_inner_failure_without_aborting_outer():
    db = make_db()
    with atomic_transaction(db):
        db.execute("INSERT INTO values_seen VALUES (1)")
        with pytest.raises(RuntimeError):
            with atomic_transaction(db):
                db.execute("INSERT INTO values_seen VALUES (2)")
                raise RuntimeError("rollback nested work")
        db.execute("INSERT INTO values_seen VALUES (3)")

    assert db.execute("SELECT value FROM values_seen ORDER BY value").fetchall() == [(1,), (3,)]
    db.close()


def test_outer_rollback_reverts_successful_nested_savepoint():
    db = make_db()
    with pytest.raises(RuntimeError):
        with atomic_transaction(db):
            db.execute("INSERT INTO values_seen VALUES (4)")
            with atomic_transaction(db):
                db.execute("INSERT INTO values_seen VALUES (5)")
            raise RuntimeError("rollback outer work")

    assert db.execute("SELECT value FROM values_seen").fetchall() == []
    db.close()


def test_atomic_transaction_commits_when_called_without_outer_transaction():
    db = make_db()
    with atomic_transaction(db):
        db.execute("INSERT INTO values_seen VALUES (6)")

    assert db.execute("SELECT value FROM values_seen").fetchall() == [(6,)]
    db.close()
