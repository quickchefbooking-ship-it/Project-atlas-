"""Explicit mapping between verified external OIDC subjects and Atlas accounts.

This module is a service/repository boundary only. It adds no HTTP routes and
never matches provider identities by email. A link can be created only from an
already authenticated Atlas session principal carrying the server-provisioned
identity:link scope, plus ID-token claims verified by the pinned OIDC verifier
and bound to a consumed one-time PKCE transaction.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .account_identity import SQLiteAccountRepository
from .atlas_session_identity import ATLAS_IDENTITY_ISSUER
from .identity_policy import AuthorizationDenied, RequestPrincipal
from .oidc_id_token_verifier import VerifiedIDTokenClaims
from .oidc_login_transaction import (
    ConsumedLoginTransaction,
    InvalidLoginTransaction,
    SQLiteOIDCLoginTransactionStore,
)


IDENTITY_LINK_SCOPE = "identity:link"


class OIDCAccountLinkError(RuntimeError):
    """Base error for explicit OIDC account-link operations."""


class OIDCAccountLinkConflict(OIDCAccountLinkError):
    """The external identity is already linked or the account has another link."""


class OIDCAccountLinkNotFound(OIDCAccountLinkError):
    """No explicit external-identity link exists."""


class InactiveAtlasAccount(OIDCAccountLinkError):
    """The Atlas account is not active and cannot be linked or authenticated."""


@dataclass(frozen=True)
class LinkedOIDCAccount:
    """Minimal server-side mapping result; no provider profile data is retained."""

    account_id: str
    issuer: str
    subject: str
    linked_at: str


def _required_exact_text(value: str, field: str, limit: int = 512) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > limit
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError(f"{field} must be exact non-empty text of at most {limit} characters.")
    return value


def _verified_identity(claims: VerifiedIDTokenClaims) -> tuple[str, str]:
    if not isinstance(claims, VerifiedIDTokenClaims):
        raise TypeError("Verified OIDC ID-token claims from the trusted verifier are required.")
    issuer = _required_exact_text(claims.issuer, "issuer")
    subject = _required_exact_text(claims.subject, "subject")
    _required_exact_text(claims.nonce, "nonce", 256)
    if (
        not isinstance(claims.audiences, tuple)
        or not claims.audiences
        or any(not isinstance(item, str) or not item for item in claims.audiences)
    ):
        raise ValueError("Verified OIDC client audiences are required.")
    return issuer, subject


class SQLiteOIDCAccountLinkRepository:
    """Persist external identity links in the Atlas account database.

    The repository accepts an initialized SQLiteAccountRepository so links
    share its account foreign key and cannot point into a different database.
    It stores only issuer, subject, account ID and link time; provider email,
    roles, tokens and profile claims are deliberately not copied.
    """

    def __init__(self, accounts: SQLiteAccountRepository):
        if not isinstance(accounts, SQLiteAccountRepository):
            raise TypeError("A trusted Atlas account repository is required.")
        self.accounts = accounts
        self.database_path = accounts.database_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def initialize(self) -> None:
        """Create additive link tables only after the Atlas account schema exists."""
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            account_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='atlas_accounts'"
            ).fetchone()
            if account_table is None:
                raise RuntimeError("Initialize the Atlas account repository before OIDC account links.")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS atlas_oidc_account_links (
                    issuer TEXT NOT NULL CHECK(length(issuer) BETWEEN 1 AND 512),
                    subject TEXT NOT NULL CHECK(length(subject) BETWEEN 1 AND 512),
                    account_id TEXT NOT NULL,
                    linked_at TEXT NOT NULL,
                    PRIMARY KEY (issuer, subject),
                    UNIQUE (account_id, issuer),
                    FOREIGN KEY (account_id) REFERENCES atlas_accounts(account_id)
                        ON DELETE RESTRICT
                );
                CREATE INDEX IF NOT EXISTS idx_atlas_oidc_account_links_account
                    ON atlas_oidc_account_links(account_id);
                CREATE TABLE IF NOT EXISTS atlas_oidc_account_link_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL CHECK(event_type = 'linked'),
                    issuer TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    actor_account_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (account_id) REFERENCES atlas_accounts(account_id)
                        ON DELETE RESTRICT,
                    FOREIGN KEY (actor_account_id) REFERENCES atlas_accounts(account_id)
                        ON DELETE RESTRICT
                );
                CREATE INDEX IF NOT EXISTS idx_atlas_oidc_account_link_events_account
                    ON atlas_oidc_account_link_events(account_id, event_id);
                """
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _record(row: sqlite3.Row) -> LinkedOIDCAccount:
        return LinkedOIDCAccount(
            account_id=row["account_id"],
            issuer=row["issuer"],
            subject=row["subject"],
            linked_at=row["linked_at"],
        )

    def link(self, account_id: str, issuer: str, subject: str) -> LinkedOIDCAccount:
        """Create a permanent explicit mapping; repeated same-account calls are idempotent."""
        account_id = _required_exact_text(account_id, "account_id")
        issuer = _required_exact_text(issuer, "issuer")
        subject = _required_exact_text(subject, "subject")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            account = conn.execute(
                "SELECT status FROM atlas_accounts WHERE account_id = ?",
                (account_id,),
            ).fetchone()
            if account is None or account["status"] != "active":
                raise InactiveAtlasAccount("An active Atlas account is required.")

            existing_identity = conn.execute(
                """SELECT account_id, issuer, subject, linked_at
                   FROM atlas_oidc_account_links WHERE issuer = ? AND subject = ?""",
                (issuer, subject),
            ).fetchone()
            if existing_identity is not None:
                if existing_identity["account_id"] != account_id:
                    raise OIDCAccountLinkConflict("External identity is already linked.")
                conn.commit()
                return self._record(existing_identity)

            existing_provider_for_account = conn.execute(
                """SELECT account_id, issuer, subject, linked_at
                   FROM atlas_oidc_account_links WHERE account_id = ? AND issuer = ?""",
                (account_id, issuer),
            ).fetchone()
            if existing_provider_for_account is not None:
                raise OIDCAccountLinkConflict("This Atlas account already has an identity from this issuer.")

            conn.execute(
                """INSERT INTO atlas_oidc_account_links
                   (issuer, subject, account_id, linked_at) VALUES (?, ?, ?, ?)""",
                (issuer, subject, account_id, now),
            )
            conn.execute(
                """INSERT INTO atlas_oidc_account_link_events
                   (event_type, issuer, subject, account_id, actor_account_id, created_at)
                   VALUES ('linked', ?, ?, ?, ?, ?)""",
                (issuer, subject, account_id, account_id, now),
            )
            conn.commit()
            return LinkedOIDCAccount(account_id, issuer, subject, now)
        except sqlite3.IntegrityError:
            if conn.in_transaction:
                conn.rollback()
            raise OIDCAccountLinkConflict("External identity could not be linked.") from None
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

    def resolve(self, issuer: str, subject: str) -> LinkedOIDCAccount:
        """Resolve only an exact prior link and require the Atlas account to remain active."""
        issuer = _required_exact_text(issuer, "issuer")
        subject = _required_exact_text(subject, "subject")
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT l.account_id, l.issuer, l.subject, l.linked_at, a.status
                   FROM atlas_oidc_account_links l
                   JOIN atlas_accounts a ON a.account_id = l.account_id
                   WHERE l.issuer = ? AND l.subject = ?""",
                (issuer, subject),
            ).fetchone()
            if row is None:
                raise OIDCAccountLinkNotFound("No explicit Atlas account link exists.")
            if row["status"] != "active":
                raise InactiveAtlasAccount("An active Atlas account is required.")
            return self._record(row)
        finally:
            conn.close()


@dataclass(frozen=True)
class OIDCAccountLinkService:
    """Enforce the Atlas-session, explicit-scope and PKCE-nonce linking boundary."""

    repository: SQLiteOIDCAccountLinkRepository
    transactions: SQLiteOIDCLoginTransactionStore

    def __post_init__(self) -> None:
        if not isinstance(self.repository, SQLiteOIDCAccountLinkRepository):
            raise TypeError("A trusted OIDC account-link repository is required.")
        if not isinstance(self.transactions, SQLiteOIDCLoginTransactionStore):
            raise TypeError("A trusted OIDC login transaction store is required.")

    def _require_nonce_bound_identity(
        self,
        claims: VerifiedIDTokenClaims,
        transaction: ConsumedLoginTransaction,
    ) -> tuple[str, str]:
        issuer, subject = _verified_identity(claims)
        if not isinstance(transaction, ConsumedLoginTransaction):
            raise InvalidLoginTransaction("Login transaction is invalid or expired.")
        if not self.transactions.nonce_matches(transaction, claims.nonce):
            raise InvalidLoginTransaction("Login transaction is invalid or expired.")
        return issuer, subject

    def link_authenticated_account(
        self,
        principal: RequestPrincipal,
        claims: VerifiedIDTokenClaims,
        transaction: ConsumedLoginTransaction,
    ) -> LinkedOIDCAccount:
        """Link only from an active Atlas session with the dedicated server scope.

        The HTTP caller must obtain principal from the existing live Atlas
        session/CSRF boundary. It must consume state and verify the ID token
        before calling this method. No account ID or provider email is accepted
        from browser input.
        """
        if (
            not isinstance(principal, RequestPrincipal)
            or principal.issuer != ATLAS_IDENTITY_ISSUER
            or not principal.membership_active
            or IDENTITY_LINK_SCOPE not in principal.scopes
        ):
            raise AuthorizationDenied("An active Atlas session with identity:link is required.")
        issuer, subject = self._require_nonce_bound_identity(claims, transaction)
        return self.repository.link(principal.subject, issuer, subject)

    def resolve_login_account(
        self,
        claims: VerifiedIDTokenClaims,
        transaction: ConsumedLoginTransaction,
    ) -> LinkedOIDCAccount:
        """Resolve an existing explicit link after the callback's nonce is matched.

        Unknown external identities are never auto-created or matched by email.
        """
        issuer, subject = self._require_nonce_bound_identity(claims, transaction)
        return self.repository.resolve(issuer, subject)
