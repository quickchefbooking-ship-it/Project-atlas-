"""Composable SQLite transaction and savepoint helper for repository writes.

When a repository method is called inside a caller-owned transaction, it uses a
savepoint instead of committing or rolling back the caller's transaction.
"""
from __future__ import annotations

from contextlib import contextmanager
import sqlite3
import uuid
from typing import Iterator


@contextmanager
def atomic_transaction(db: sqlite3.Connection) -> Iterator[None]:
    """Begin/commit a transaction, or isolate nested work with a savepoint."""
    if db.in_transaction:
        savepoint = "professor_sp_" + uuid.uuid4().hex
        db.execute(f"SAVEPOINT {savepoint}")
        try:
            yield
        except BaseException:
            try:
                db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            finally:
                db.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise
        else:
            db.execute(f"RELEASE SAVEPOINT {savepoint}")
        return

    db.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        db.rollback()
        raise
    else:
        try:
            db.commit()
        except BaseException:
            db.rollback()
            raise
