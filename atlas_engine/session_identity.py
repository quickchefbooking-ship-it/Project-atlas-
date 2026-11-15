"""Atlas Identity server-side session primitives.

Raw bearer credentials are returned only to trusted server code. The database stores
SHA-256 digests, never session secrets. This module deliberately exposes no HTTP
routes or cookie handling; those require the separate browser/CSRF integration stage.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


class SessionError(RuntimeError):
    """Base session-store error."""


class InvalidSession(SessionError):
    """Missing, expired, revoked, rotated, or ineligible session."""


@dataclass(frozen=True)
class IssuedSession:
    token: str
    session_id: str
    account_id: str
    created_at: str
    idle_expires_at: str
    absolute_expires_at: str


@dataclass(frozen=True)
class ValidatedSession:
    session_id: str
    account_id: str
    created_at: str
    idle_expires_at: str
    absolute_expires_at: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _digest(token: str) -> str:
    if not isinstance(token, str) or not 40 <= len(token) <= 256:
        raise InvalidSession("Session is invalid or expired.")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SQLiteSessionRepository:
    """Server-side opaque sessions in the dedicated Atlas account database."""

    def __init__(
        self,
        database_path: str,
        *,
        idle_timeout: timedelta = timedelta(minutes=30),
        absolute_timeout: timedelta = timedelta(hours=12),
    ):
        if not isinstance(database_path, str) or not database_path.strip():
            raise ValueError("A dedicated Atlas account database path is required.")
        if not isinstance(idle_timeout, timedelta) or not timedelta(minutes=1) <= idle_timeout <= timedelta(days=1):
            raise ValueError("Idle timeout must be between one minute and one day.")
        if not isinstance(absolute_timeout, timedelta) or not idle_timeout <= absolute_timeout <= timedelta(days=30):
            raise ValueError("Absolute timeout must be at least the idle timeout and no more than 30 days.")
        self.database_path = database_path
        self.idle_timeout = idle_timeout
        self.absolute_timeout = absolute_timeout

    def _connect(self):
        conn = sqlite3.connect(self.database_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def initialize(self) -> None:
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS atlas_sessions (
                    session_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    idle_expires_at TEXT NOT NULL,
                    absolute_expires_at TEXT NOT NULL,
                    revoked_at TEXT,
                    rotated_to_session_id TEXT,
                    FOREIGN KEY(account_id) REFERENCES atlas_accounts(account_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_atlas_sessions_account ON atlas_sessions(account_id, revoked_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_atlas_sessions_expiry ON atlas_sessions(idle_expires_at, absolute_expires_at)")
            conn.commit()
        finally:
            conn.close()

    def _insert(self, conn: sqlite3.Connection, account_id: str, now: datetime) -> IssuedSession:
        account = conn.execute(
            "SELECT status FROM atlas_accounts WHERE account_id=?", (account_id,)
        ).fetchone()
        if account is None or account["status"] != "active":
            raise InvalidSession("Session is invalid or expired.")
        token = secrets.token_urlsafe(48)
        session_id = str(uuid.uuid4())
        idle_expiry = min(now + self.idle_timeout, now + self.absolute_timeout)
        absolute_expiry = now + self.absolute_timeout
        conn.execute(
            """INSERT INTO atlas_sessions
               (session_id,account_id,token_hash,created_at,last_seen_at,idle_expires_at,absolute_expires_at)
               VALUES (?,?,?,?,?,?,?)""",
            (session_id, account_id, hashlib.sha256(token.encode("utf-8")).hexdigest(),
             _stamp(now), _stamp(now), _stamp(idle_expiry), _stamp(absolute_expiry)),
        )
        return IssuedSession(token, session_id, account_id, _stamp(now), _stamp(idle_expiry), _stamp(absolute_expiry))

    def issue_session(self, account_id: str) -> IssuedSession:
        now = _now()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            issued = self._insert(conn, account_id, now)
            conn.commit()
            return issued
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def validate_session(self, token: str) -> ValidatedSession:
        digest = _digest(token)
        now = _now()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT s.*,a.status FROM atlas_sessions s
                   JOIN atlas_accounts a ON a.account_id=s.account_id
                   WHERE s.token_hash=?""", (digest,)
            ).fetchone()
            if (row is None or row["revoked_at"] is not None
                    or row["rotated_to_session_id"] is not None
                    or row["status"] != "active"):
                raise InvalidSession("Session is invalid or expired.")
            try:
                idle_expiry = datetime.fromisoformat(row["idle_expires_at"])
                absolute_expiry = datetime.fromisoformat(row["absolute_expires_at"])
            except (TypeError, ValueError):
                raise InvalidSession("Session is invalid or expired.") from None
            if (idle_expiry.tzinfo is None or absolute_expiry.tzinfo is None
                    or idle_expiry <= now or absolute_expiry <= now):
                conn.execute(
                    "UPDATE atlas_sessions SET revoked_at=? WHERE session_id=? AND revoked_at IS NULL",
                    (_stamp(now), row["session_id"]),
                )
                conn.commit()
                raise InvalidSession("Session is invalid or expired.")
            next_idle = min(now + self.idle_timeout, absolute_expiry)
            conn.execute(
                "UPDATE atlas_sessions SET last_seen_at=?,idle_expires_at=? WHERE session_id=?",
                (_stamp(now), _stamp(next_idle), row["session_id"]),
            )
            conn.commit()
            return ValidatedSession(row["session_id"], row["account_id"], row["created_at"],
                                    _stamp(next_idle), row["absolute_expires_at"])
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def revoke_session(self, token: str) -> bool:
        digest = _digest(token)
        conn = self._connect()
        try:
            cursor = conn.execute(
                """UPDATE atlas_sessions SET revoked_at=?
                   WHERE token_hash=? AND revoked_at IS NULL AND rotated_to_session_id IS NULL""",
                (_stamp(_now()), digest),
            )
            conn.commit()
            return cursor.rowcount == 1
        finally:
            conn.close()

    def revoke_all_sessions(self, account_id: str) -> int:
        conn = self._connect()
        try:
            cursor = conn.execute(
                """UPDATE atlas_sessions SET revoked_at=?
                   WHERE account_id=? AND revoked_at IS NULL""",
                (_stamp(_now()), account_id),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def rotate_session(self, token: str) -> IssuedSession:
        """Atomically retire an existing session and issue its replacement."""
        digest = _digest(token)
        now = _now()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT s.*,a.status FROM atlas_sessions s
                   JOIN atlas_accounts a ON a.account_id=s.account_id
                   WHERE s.token_hash=?""", (digest,)
            ).fetchone()
            if (row is None or row["revoked_at"] is not None
                    or row["rotated_to_session_id"] is not None
                    or row["status"] != "active"):
                raise InvalidSession("Session is invalid or expired.")
            try:
                idle_expiry = datetime.fromisoformat(row["idle_expires_at"])
                absolute_expiry = datetime.fromisoformat(row["absolute_expires_at"])
            except (TypeError, ValueError):
                raise InvalidSession("Session is invalid or expired.") from None
            if (idle_expiry.tzinfo is None or absolute_expiry.tzinfo is None
                    or idle_expiry <= now or absolute_expiry <= now):
                raise InvalidSession("Session is invalid or expired.")
            replacement = self._insert(conn, row["account_id"], now)
            conn.execute(
                """UPDATE atlas_sessions SET revoked_at=?,rotated_to_session_id=?
                   WHERE session_id=? AND revoked_at IS NULL""",
                (_stamp(now), replacement.session_id, row["session_id"]),
            )
            conn.commit()
            return replacement
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
