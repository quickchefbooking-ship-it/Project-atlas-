"""Atlas-owned account and credential primitives.

This module is intentionally not wired to HTTP routes. It stores password hashes
only, uses Argon2id via argon2-cffi, and keeps account data separate from task,
conversation and tenant-membership databases. Public registration/login must not
be enabled until the session, CSRF, verification and abuse-control stages land.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
                CREATE TABLE IF NOT EXISTS atlas_account_tokens (
                    token_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    purpose TEXT NOT NULL CHECK(purpose IN ('email_verification','password_recovery')),
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(account_id) REFERENCES atlas_accounts(account_id)
                );
                CREATE INDEX IF NOT EXISTS idx_atlas_account_tokens_account_purpose
                    ON atlas_account_tokens(account_id, purpose, consumed_at);
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

    @staticmethod
    def _token_digest(token: str) -> str:
        if not isinstance(token, str) or len(token) < 32 or len(token) > 256:
            raise ValueError("A valid one-time token is required.")
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _issue_token(self, account_id: str, purpose: str, *, lifetime: timedelta) -> str:
        if purpose not in {"email_verification", "password_recovery"}:
            raise ValueError("Unsupported account-token purpose.")
        if not isinstance(lifetime, timedelta) or lifetime <= timedelta(0) or lifetime > timedelta(days=7):
            raise ValueError("Token lifetime must be positive and no longer than seven days.")
        token = secrets.token_urlsafe(32)
        digest = self._token_digest(token)
        now = datetime.now(timezone.utc)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            account = conn.execute(
                "SELECT status FROM atlas_accounts WHERE account_id=?", (account_id,)
            ).fetchone()
            if account is None:
                raise AccountNotFound("Account was not found.")
            if purpose == "email_verification" and account["status"] != "pending_verification":
                raise AccountStoreError("Only pending accounts can receive verification tokens.")
            if purpose == "password_recovery" and account["status"] != "active":
                raise AccountNotFound("Account was not found.")
            conn.execute(
                """UPDATE atlas_account_tokens SET consumed_at=?
                   WHERE account_id=? AND purpose=? AND consumed_at IS NULL""",
                (now.isoformat(timespec="seconds"), account_id, purpose),
            )
            conn.execute(
                """INSERT INTO atlas_account_tokens
                   (token_id,account_id,purpose,token_hash,expires_at,created_at)
                   VALUES (?,?,?,?,?,?)""",
                (str(uuid.uuid4()), account_id, purpose, digest,
                 (now + lifetime).isoformat(timespec="seconds"),
                 now.isoformat(timespec="seconds")),
            )
            conn.commit()
            return token
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def issue_email_verification_token(self, account_id: str, *, lifetime: timedelta = timedelta(hours=24)) -> str:
        """Return a one-time token to trusted delivery code; persist only its hash."""
        return self._issue_token(account_id, "email_verification", lifetime=lifetime)

    def issue_password_recovery_token(self, email: str, *, lifetime: timedelta = timedelta(minutes=30)) -> Optional[str]:
        """Return None for unknown/ineligible accounts to support generic HTTP responses."""
        normalized = normalize_email(email)
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT account_id,status FROM atlas_accounts WHERE email_normalized=?",
                (normalized,),
            ).fetchone()
        finally:
            conn.close()
        if row is None or row["status"] != "active":
            return None
        return self._issue_token(row["account_id"], "password_recovery", lifetime=lifetime)

    def verify_email(self, token: str) -> AccountRecord:
        """Consume a single-use verification token and activate its pending account."""
        digest = self._token_digest(token)
        now = datetime.now(timezone.utc)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT t.token_id,t.account_id,t.expires_at,t.consumed_at,a.status
                   FROM atlas_account_tokens t JOIN atlas_accounts a ON a.account_id=t.account_id
                   WHERE t.token_hash=? AND t.purpose='email_verification'""",
                (digest,),
            ).fetchone()
            if row is None or row["consumed_at"] is not None or row["status"] != "pending_verification":
                raise InvalidCredential("One-time token is invalid or expired.")
            try:
                expiry = datetime.fromisoformat(row["expires_at"])
            except (TypeError, ValueError):
                raise InvalidCredential("One-time token is invalid or expired.") from None
            if expiry.tzinfo is None or expiry <= now:
                conn.execute(
                    "UPDATE atlas_account_tokens SET consumed_at=? WHERE token_id=?",
                    (now.isoformat(timespec="seconds"), row["token_id"]),
                )
                conn.commit()
                raise InvalidCredential("One-time token is invalid or expired.")
            now_text = now.isoformat(timespec="seconds")
            conn.execute(
                "UPDATE atlas_account_tokens SET consumed_at=? WHERE token_id=? AND consumed_at IS NULL",
                (now_text, row["token_id"]),
            )
            conn.execute(
                """UPDATE atlas_accounts SET status='active',updated_at=?
                   WHERE account_id=? AND status='pending_verification'""",
                (now_text, row["account_id"]),
            )
            conn.commit()
            account = conn.execute(
                """SELECT account_id,email_normalized,status,created_at,updated_at
                   FROM atlas_accounts WHERE account_id=?""",
                (row["account_id"],),
            ).fetchone()
            return AccountRecord(account["account_id"], account["email_normalized"], account["status"], account["created_at"], account["updated_at"])
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def reset_password(self, token: str, new_password: str) -> None:
        """Consume recovery token, replace hash and invalidate all outstanding tokens."""
        replacement = self.hasher.hash(new_password)
        digest = self._token_digest(token)
        now = datetime.now(timezone.utc)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT t.token_id,t.account_id,t.expires_at,t.consumed_at,a.status
                   FROM atlas_account_tokens t JOIN atlas_accounts a ON a.account_id=t.account_id
                   WHERE t.token_hash=? AND t.purpose='password_recovery'""",
                (digest,),
            ).fetchone()
            if row is None or row["consumed_at"] is not None or row["status"] != "active":
                raise InvalidCredential("One-time token is invalid or expired.")
            try:
                expiry = datetime.fromisoformat(row["expires_at"])
            except (TypeError, ValueError):
                raise InvalidCredential("One-time token is invalid or expired.") from None
            if expiry.tzinfo is None or expiry <= now:
                raise InvalidCredential("One-time token is invalid or expired.")
            now_text = now.isoformat(timespec="seconds")
            conn.execute(
                """UPDATE atlas_accounts SET password_hash=?,password_changed_at=?,updated_at=?
                   WHERE account_id=? AND status='active'""",
                (replacement, now_text, now_text, row["account_id"]),
            )
            conn.execute(
                """UPDATE atlas_account_tokens SET consumed_at=?
                   WHERE account_id=? AND consumed_at IS NULL""",
                (now_text, row["account_id"]),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
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
