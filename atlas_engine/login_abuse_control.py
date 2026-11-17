"""Persistent, privacy-preserving login abuse controls.

This component is deliberately not wired to public HTTP routes yet. Callers must
check before password verification, record failures, and clear only the account
bucket after successful authentication. Network buckets are never cleared by a
successful login. The HMAC key must be supplied from deployment secret storage.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import math
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class AbuseDecision:
    allowed: bool
    retry_after_seconds: int = 0


class SQLiteLoginAbuseGuard:
    """Atomic fixed-window throttling for account and network identifiers."""

    def __init__(
        self,
        database_path: str,
        *,
        hmac_key: bytes,
        max_failures: int = 5,
        window_seconds: int = 900,
        lockout_seconds: int = 900,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if not isinstance(database_path, str) or not database_path.strip():
            raise ValueError("A dedicated abuse-control database path is required.")
        if not isinstance(hmac_key, bytes) or len(hmac_key) < 32:
            raise ValueError("A secret HMAC key of at least 32 bytes is required.")
        if not (1 <= max_failures <= 100):
            raise ValueError("max_failures must be between 1 and 100.")
        if not (1 <= window_seconds <= 86400 and 1 <= lockout_seconds <= 86400):
            raise ValueError("Window and lockout must be between 1 and 86400 seconds.")
        self.database_path = database_path
        self._key = hmac_key
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._clock = clock or time.time

    def _connect(self):
        conn = sqlite3.connect(self.database_path, timeout=10)
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def initialize(self) -> None:
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS atlas_login_abuse_buckets (
                    bucket_key TEXT PRIMARY KEY,
                    window_started REAL NOT NULL,
                    failures INTEGER NOT NULL CHECK(failures >= 0),
                    blocked_until REAL NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_atlas_login_abuse_blocked
                ON atlas_login_abuse_buckets(blocked_until)
            """)

    @staticmethod
    def _validate(value: str, label: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 512:
            raise ValueError(f"A valid {label} is required.")
        return value.strip().casefold()

    @staticmethod
    def _normalize_network_source(value: str) -> str:
        """Canonicalize a server-derived client IP before creating its bucket key."""
        if not isinstance(value, str) or not value.strip() or len(value) > 512:
            raise ValueError("A valid network IP address is required.")
        try:
            address = ipaddress.ip_address(value.strip())
        except ValueError:
            raise ValueError("A valid network IP address is required.") from None

        if isinstance(address, ipaddress.IPv6Address):
            if address.scope_id is not None:
                raise ValueError("Scoped network IP addresses are not supported.")
            # IPv4-mapped IPv6 and native IPv4 must share one abuse bucket.
            if address.ipv4_mapped is not None:
                address = address.ipv4_mapped
        return address.compressed

    def _digest(self, kind: str, value: str) -> str:
        message = f"atlas-login-abuse-v1:{kind}:{value}".encode("utf-8")
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    def _keys(self, identifier: str, source: str) -> tuple[str, str]:
        account = self._validate(identifier, "account identifier")
        network = self._normalize_network_source(source)
        return self._digest("account", account), self._digest("network", network)

    def check(self, identifier: str, source: str) -> AbuseDecision:
        keys = self._keys(identifier, source)
        now = float(self._clock())
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT blocked_until FROM atlas_login_abuse_buckets WHERE bucket_key IN (?,?)",
                keys,
            ).fetchall()
        retry = max((float(row[0]) - now for row in rows), default=0.0)
        return AbuseDecision(retry <= 0, max(0, math.ceil(retry)))

    def record_failure(self, identifier: str, source: str) -> AbuseDecision:
        keys = self._keys(identifier, source)
        now = float(self._clock())
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            retry = 0.0
            for key in keys:
                row = conn.execute(
                    "SELECT window_started,failures,blocked_until FROM atlas_login_abuse_buckets WHERE bucket_key=?",
                    (key,),
                ).fetchone()
                if row and float(row[2]) > now:
                    retry = max(retry, float(row[2]) - now)
                    continue
                if row is None or now - float(row[0]) >= self.window_seconds:
                    started, failures = now, 1
                else:
                    started, failures = float(row[0]), int(row[1]) + 1
                blocked_until = now + self.lockout_seconds if failures >= self.max_failures else 0.0
                conn.execute(
                    """INSERT INTO atlas_login_abuse_buckets
                       (bucket_key,window_started,failures,blocked_until) VALUES (?,?,?,?)
                       ON CONFLICT(bucket_key) DO UPDATE SET
                         window_started=excluded.window_started,
                         failures=excluded.failures,
                         blocked_until=excluded.blocked_until""",
                    (key, started, failures, blocked_until),
                )
                retry = max(retry, blocked_until - now)
            conn.commit()
            return AbuseDecision(retry <= 0, max(0, math.ceil(retry)))
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record_success(self, identifier: str) -> None:
        """Clear only the account bucket; do not erase network-wide abuse history."""
        account = self._validate(identifier, "account identifier")
        key = self._digest("account", account)
        with self._connect() as conn:
            conn.execute("DELETE FROM atlas_login_abuse_buckets WHERE bucket_key=?", (key,))

    def purge_expired(self, *, now: float | None = None) -> int:
        """Bound storage growth by deleting buckets past both window and lockout."""
        current = float(self._clock() if now is None else now)
        cutoff = current - self.window_seconds
        with self._connect() as conn:
            cursor = conn.execute(
                """DELETE FROM atlas_login_abuse_buckets
                   WHERE window_started < ? AND blocked_until <= ?""",
                (cutoff, current),
            )
            return int(cursor.rowcount)
