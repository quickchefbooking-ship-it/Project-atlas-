"""Short-lived server-side OIDC Authorization Code + PKCE transactions.

This module is a storage primitive only. It does not perform provider discovery,
HTTP redirects, code exchange, ID-token verification, membership lookup, or
Atlas session issuance. A future route must keep the verifier server-side,
consume state exactly once, verify the ID-token nonce, and then use the
existing verified-identity and session services.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


DEFAULT_TTL_SECONDS = 300
MIN_TTL_SECONDS = 60
MAX_TTL_SECONDS = 900
_STATE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,256}$")
_NONCE_BYTES = 12


class LoginTransactionError(RuntimeError):
    """Base error for short-lived hosted-login transaction operations."""


class InvalidLoginTransaction(LoginTransactionError):
    """Unknown, expired, replayed, or cryptographically invalid transaction."""


@dataclass(frozen=True)
class LoginTransactionStart:
    """Values for a trusted server route to construct the provider redirect."""

    state: str = field(repr=False)
    nonce: str = field(repr=False)
    code_verifier: str = field(repr=False)
    code_challenge: str
    expires_at: int


@dataclass(frozen=True)
class ConsumedLoginTransaction:
    """One-time callback material returned only to trusted server code."""

    code_verifier: str = field(repr=False)
    nonce_digest: str = field(repr=False)
    created_at: int
    expires_at: int


class SQLiteOIDCLoginTransactionStore:
    """Encrypted, one-time OIDC login transactions in a dedicated SQLite file.

    The caller supplies a dedicated 32-byte key from deployment secret
    management. Separate HMAC-derived keys protect state/nonce digests and
    AES-256-GCM protects the recoverable PKCE verifier.
    """

    def __init__(
        self,
        database_path: str,
        encryption_key: bytes,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        clock: Optional[Callable[[], float]] = None,
    ):
        if not isinstance(database_path, str) or not database_path.strip() or database_path == ":memory:":
            raise ValueError("A dedicated file-backed login transaction database path is required.")
        if not isinstance(encryption_key, bytes) or len(encryption_key) != 32:
            raise ValueError("A dedicated 32-byte login transaction encryption key is required.")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not MIN_TTL_SECONDS <= ttl_seconds <= MAX_TTL_SECONDS:
            raise ValueError("Login transaction TTL must be between 60 and 900 seconds.")
        if clock is not None and not callable(clock):
            raise ValueError("clock must be callable.")

        self.database_path = database_path
        self.ttl_seconds = ttl_seconds
        self._clock = clock or time.time
        self._state_key = hmac.new(
            encryption_key, b"atlas-oidc-login-state-v1", hashlib.sha256
        ).digest()
        self._verifier_key = hmac.new(
            encryption_key, b"atlas-oidc-login-verifier-v1", hashlib.sha256
        ).digest()

    def _now(self) -> int:
        value = self._clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RuntimeError("Login transaction clock returned an invalid timestamp.")
        return int(value)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def initialize(self) -> None:
        """Create the isolated transaction table; never called implicitly."""
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS atlas_oidc_login_transactions (
                    transaction_id TEXT PRIMARY KEY,
                    state_digest TEXT NOT NULL UNIQUE,
                    nonce_digest TEXT NOT NULL,
                    verifier_nonce BLOB NOT NULL CHECK(length(verifier_nonce) = 12),
                    verifier_ciphertext BLOB NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    consumed_at INTEGER,
                    CHECK(expires_at > created_at)
                );
                CREATE INDEX IF NOT EXISTS idx_oidc_login_transactions_expiry
                    ON atlas_oidc_login_transactions(expires_at, consumed_at);
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _digest(self, purpose: str, value: str) -> str:
        return hmac.new(
            self._state_key,
            (purpose + ":" + value).encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _associated_data(transaction_id: str, state_digest: str) -> bytes:
        return f"atlas-oidc-login-v1:{transaction_id}:{state_digest}".encode("ascii")

    def begin(self) -> LoginTransactionStart:
        """Create state, nonce and S256 PKCE material for one login attempt.

        The returned code verifier is for server-side use only. It must never
        be placed in a browser URL, cookie, HTML response, or application log.
        """
        now = self._now()
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(48)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        transaction_id = uuid.uuid4().hex
        state_digest = self._digest("state", state)
        nonce_digest = self._digest("nonce", nonce)
        verifier_nonce = secrets.token_bytes(_NONCE_BYTES)
        verifier_ciphertext = AESGCM(self._verifier_key).encrypt(
            verifier_nonce,
            code_verifier.encode("ascii"),
            self._associated_data(transaction_id, state_digest),
        )
        expires_at = now + self.ttl_seconds

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Expired rows are no longer useful. Consumed rows remain until
            # expiry so repeated callbacks are distinguishable during the TTL.
            conn.execute(
                "DELETE FROM atlas_oidc_login_transactions WHERE expires_at <= ?",
                (now,),
            )
            conn.execute(
                """INSERT INTO atlas_oidc_login_transactions
                   (transaction_id,state_digest,nonce_digest,verifier_nonce,
                    verifier_ciphertext,created_at,expires_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    transaction_id,
                    state_digest,
                    nonce_digest,
                    verifier_nonce,
                    verifier_ciphertext,
                    now,
                    expires_at,
                ),
            )
            conn.commit()
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

        return LoginTransactionStart(
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
            code_challenge=code_challenge,
            expires_at=expires_at,
        )

    def consume(self, state: str) -> ConsumedLoginTransaction:
        """Atomically consume a valid state and recover its PKCE verifier once."""
        if not isinstance(state, str) or not _STATE_PATTERN.fullmatch(state):
            raise InvalidLoginTransaction("Login transaction is invalid or expired.")

        now = self._now()
        state_digest = self._digest("state", state)
        conn = self._connect()
        stored = None
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT transaction_id,nonce_digest,verifier_nonce,
                          verifier_ciphertext,created_at,expires_at,consumed_at
                   FROM atlas_oidc_login_transactions WHERE state_digest = ?""",
                (state_digest,),
            ).fetchone()
            if row is None or row["consumed_at"] is not None:
                conn.commit()
                raise InvalidLoginTransaction("Login transaction is invalid or expired.")
            if row["expires_at"] <= now:
                conn.execute(
                    """UPDATE atlas_oidc_login_transactions SET consumed_at = ?
                       WHERE transaction_id = ? AND consumed_at IS NULL""",
                    (now, row["transaction_id"]),
                )
                conn.commit()
                raise InvalidLoginTransaction("Login transaction is invalid or expired.")

            updated = conn.execute(
                """UPDATE atlas_oidc_login_transactions SET consumed_at = ?
                   WHERE transaction_id = ? AND consumed_at IS NULL AND expires_at > ?""",
                (now, row["transaction_id"], now),
            )
            if updated.rowcount != 1:
                conn.commit()
                raise InvalidLoginTransaction("Login transaction is invalid or expired.")
            stored = dict(row)
            conn.commit()
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

        # Consumption is committed before decryption. Corrupt ciphertext can
        # never make a failed callback reusable.
        try:
            code_verifier = AESGCM(self._verifier_key).decrypt(
                bytes(stored["verifier_nonce"]),
                bytes(stored["verifier_ciphertext"]),
                self._associated_data(stored["transaction_id"], state_digest),
            ).decode("ascii")
        except (InvalidTag, ValueError, UnicodeDecodeError):
            raise InvalidLoginTransaction("Login transaction is invalid or expired.") from None

        return ConsumedLoginTransaction(
            code_verifier=code_verifier,
            nonce_digest=stored["nonce_digest"],
            created_at=stored["created_at"],
            expires_at=stored["expires_at"],
        )

    def nonce_matches(self, transaction: ConsumedLoginTransaction, candidate_nonce: str) -> bool:
        """Constant-time comparison of a verified ID-token nonce to the stored nonce."""
        if not isinstance(transaction, ConsumedLoginTransaction):
            return False
        if not isinstance(candidate_nonce, str) or not _STATE_PATTERN.fullmatch(candidate_nonce):
            return False
        if not isinstance(transaction.nonce_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", transaction.nonce_digest):
            return False
        candidate_digest = self._digest("nonce", candidate_nonce)
        return hmac.compare_digest(transaction.nonce_digest, candidate_digest)
