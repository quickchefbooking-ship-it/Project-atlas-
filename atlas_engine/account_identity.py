"""Atlas-owned account and credential primitives.

This module is intentionally not wired to HTTP routes. It stores password hashes
only, uses Argon2id via argon2-cffi, and keeps account data separate from task,
conversation and tenant-membership databases. Public registration/login must not
be enabled until the session, CSRF, verification and abuse-control stages land.
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class AccountStoreError(RuntimeError):
    """Base error for account-store operations."""


class AccountAlreadyExists(AccountStoreError):
    """An account with this normalized email already exists."""


class AccountNotFound(AccountStoreError):
    """The requested account does not exist."""


class InvalidCredential(AccountStoreError):
    """Credential verification failed; callers should return a generic response."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_email(email: str) -> str:
    if not isinstance(email, str):
        raise ValueError("Email must be text.")
    value = email.strip().casefold()
    if len(value) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise ValueError("A valid email address is required.")
    return value


class Argon2idCredentialHasher:
    """Versioned Argon2id password hashing with safe verification semantics."""

    def __init__(self, *, time_cost: int = 3, memory_cost: int = 65536, parallelism: int = 2):
        if not (1 <= time_cost <= 10 and 19456 <= memory_cost <= 1048576 and 1 <= parallelism <= 8):
            raise ValueError("Argon2id parameters are outside the permitted safety bounds.")
        self._hasher = PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )

    @staticmethod
    def _validate_password(password: str) -> None:
        if not isinstance(password, str) or len(password) < 12 or len(password) > 1024:
            raise ValueError("Password must contain between 12 and 1024 characters.")

    def hash(self, password: str) -> str:
        self._validate_password(password)
        return self._hasher.hash(password)

    def verify(self, encoded_hash: str, password: str) -> bool:
        self._validate_password(password)
        if not isinstance(encoded_hash, str) or not encoded_hash.startswith("$argon2id$"):
            raise InvalidCredential("Credential verification failed.")
        try:
            return self._hasher.verify(encoded_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, encoded_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(encoded_hash)
        except (VerificationError, InvalidHashError):
            return True


@dataclass(frozen=True)
class AccountRecord:
    account_id: str
    email: str
    status: str
    created_at: str
    updated_at: str


class SQLiteAccountRepository:
    """Isolated account repository; callers supply a dedicated database path."""

    def __init__(self, database_path: str, hasher: Optional[Argon2idCredentialHasher] = None):
        if not isinstance(database_path, str) or not database_path.strip():
            raise ValueError("A dedicated account database path is required.")
        self.database_path = database_path
        self.hasher = hasher or Argon2idCredentialHasher()

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
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS atlas_accounts (
                    account_id TEXT PRIMARY KEY,
                    email_normalized TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending_verification','active','suspended','closed')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    password_changed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_atlas_accounts_status
                    ON atlas_accounts(status);
            """)
            conn.commit()
        finally:
            conn.close()

    def create_pending_account(self, email: str, password: str) -> AccountRecord:
        normalized = normalize_email(email)
        encoded = self.hasher.hash(password)
        now = _utc_now()
        account_id = str(uuid.uuid4())
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO atlas_accounts
                   (account_id,email_normalized,password_hash,status,created_at,updated_at,password_changed_at)
                   VALUES (?,?,?,'pending_verification',?,?,?)""",
                (account_id, normalized, encoded, now, now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise AccountAlreadyExists("Account already exists.") from None
        finally:
            conn.close()
        return AccountRecord(account_id, normalized, "pending_verification", now, now)

    def get_credential_record(self, email: str):
        """Internal authentication lookup; never serialize this result to a client."""
        normalized = normalize_email(email)
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT account_id,email_normalized,password_hash,status
                   FROM atlas_accounts WHERE email_normalized = ?""",
                (normalized,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def verify_password(self, email: str, password: str) -> AccountRecord:
        record = self.get_credential_record(email)
        if record is None or record["status"] != "active":
            raise InvalidCredential("Credential verification failed.")
        try:
            valid = self.hasher.verify(record["password_hash"], password)
        except ValueError:
            valid = False
        if not valid:
            raise InvalidCredential("Credential verification failed.")
        now = _utc_now()
        conn = self._connect()
        try:
            if self.hasher.needs_rehash(record["password_hash"]):
                replacement = self.hasher.hash(password)
                conn.execute(
                    """UPDATE atlas_accounts SET password_hash=?,updated_at=?
                       WHERE account_id=? AND password_hash=?""",
                    (replacement, now, record["account_id"], record["password_hash"]),
                )
            row = conn.execute(
                """SELECT account_id,email_normalized,status,created_at,updated_at
                   FROM atlas_accounts WHERE account_id=?""",
                (record["account_id"],),
            ).fetchone()
            conn.commit()
            if row is None or row["status"] != "active":
                raise InvalidCredential("Credential verification failed.")
            return AccountRecord(row["account_id"], row["email_normalized"], row["status"], row["created_at"], row["updated_at"])
        finally:
            conn.close()

    def set_account_status(self, account_id: str, status: str) -> None:
        if status not in {"pending_verification", "active", "suspended", "closed"}:
            raise ValueError("Unsupported account status.")
        now = _utc_now()
        conn = self._connect()
        try:
            cursor = conn.execute(
                "UPDATE atlas_accounts SET status=?,updated_at=? WHERE account_id=?",
                (status, now, account_id),
            )
            if cursor.rowcount != 1:
                raise AccountNotFound("Account was not found.")
            conn.commit()
        finally:
            conn.close()
