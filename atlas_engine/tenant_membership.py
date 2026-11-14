"""Server-controlled tenant membership registry.

This is an isolated persistence primitive, not an authentication adapter.
It never validates tokens or constructs RequestPrincipal objects. Only trusted
administrative/provisioning code may write memberships and scopes.
"""
from dataclasses import dataclass
import json
import sqlite3
from typing import FrozenSet, Optional


class MembershipNotFoundError(LookupError):
    """No membership exists for the verified issuer/subject pair."""


class InactiveMembershipError(PermissionError):
    """The matching membership has been revoked or disabled."""


class AmbiguousMembershipError(PermissionError):
    """A verified identity has multiple active tenants and no tenant was selected."""


@dataclass(frozen=True)
class MembershipRecord:
    issuer: str
    subject: str
    tenant_id: str
    active: bool
    scopes: FrozenSet[str]


def _required_text(value: str, field: str, limit: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{field} must be a non-empty string of at most {limit} characters.")
    return value.strip()


def _validate_scopes(scopes) -> FrozenSet[str]:
    if isinstance(scopes, (str, bytes)):
        raise ValueError("Scopes must be an iterable of scope strings, not a string.")
    try:
        result = frozenset(scopes)
    except (TypeError, ValueError):
        raise ValueError("Scopes must be a valid iterable of strings.") from None
    if any(not isinstance(s, str) or not s.strip() or len(s) > 128 for s in result):
        raise ValueError("Each scope must be a non-empty string of at most 128 characters.")
    return result


class SQLiteMembershipRegistry:
    """Small registry backed by a caller-selected SQLite database path.

    Production integration must use a separately provisioned database/path,
    backups, access controls and reviewed migrations. This class does not
    initialize or modify Professor's existing task database automatically.
    """

    def __init__(self, database_path: str):
        self.database_path = _required_text(database_path, "database_path", 2048)

    def _connect(self):
        conn = sqlite3.connect(self.database_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        conn = self._connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tenant_registry (
                    tenant_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    active INTEGER NOT NULL CHECK(active IN (0, 1))
                );
                CREATE TABLE IF NOT EXISTS tenant_memberships (
                    issuer TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    active INTEGER NOT NULL CHECK(active IN (0, 1)),
                    scopes_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (issuer, subject, tenant_id),
                    FOREIGN KEY (tenant_id) REFERENCES tenant_registry(tenant_id)
                );
                CREATE INDEX IF NOT EXISTS idx_memberships_identity_active
                    ON tenant_memberships(issuer, subject, active);
                CREATE TABLE IF NOT EXISTS membership_audit_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    issuer TEXT,
                    subject TEXT,
                    details_json TEXT NOT NULL,
                    actor_issuer TEXT,
                    actor_subject TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_membership_audit_tenant_time
                    ON membership_audit_events(tenant_id, event_id);
            """)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _record_audit(conn, event_type, tenant_id, issuer=None, subject=None, details=None):
        """Append a minimal event in the same transaction as the mutation.

        Actor identity is intentionally NULL until a verified admin principal
        exists. Never treat caller-supplied actor labels as authenticated.
        """
        conn.execute(
            """INSERT INTO membership_audit_events
               (event_type, tenant_id, issuer, subject, details_json)
               VALUES (?, ?, ?, ?, ?)""",
            (event_type, tenant_id, issuer, subject,
             json.dumps(details or {}, sort_keys=True, separators=(",", ":"))),
        )

    def list_audit_events(self, tenant_id: str):
        """Return minimal audit events for a tenant, oldest first."""
        tenant_id = _required_text(tenant_id, "tenant_id")
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT event_id, event_type, tenant_id, issuer, subject,
                          details_json, actor_issuer, actor_subject, created_at
                   FROM membership_audit_events WHERE tenant_id = ?
                   ORDER BY event_id""",
                (tenant_id,),
            ).fetchall()
            return [
                {**dict(row), "details": json.loads(row["details_json"])}
                for row in rows
            ]
        finally:
            conn.close()

    def create_tenant(self, tenant_id: str, display_name: str) -> None:
        tenant_id = _required_text(tenant_id, "tenant_id")
        display_name = _required_text(display_name, "display_name", 200)
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO tenant_registry(tenant_id, display_name, active) VALUES (?, ?, 1)",
                (tenant_id, display_name),
            )
            self._record_audit(conn, "tenant.created", tenant_id,
                               details={"display_name": display_name})
            conn.commit()
        finally:
            conn.close()

    def set_tenant_active(self, tenant_id: str, active: bool) -> None:
        tenant_id = _required_text(tenant_id, "tenant_id")
        if not isinstance(active, bool):
            raise ValueError("active must be a boolean.")
        conn = self._connect()
        try:
            cur = conn.execute(
                "UPDATE tenant_registry SET active = ? WHERE tenant_id = ?",
                (int(active), tenant_id),
            )
            if cur.rowcount != 1:
                raise MembershipNotFoundError("Tenant was not found.")
            self._record_audit(conn, "tenant.activated" if active else "tenant.deactivated",
                               tenant_id, details={"active": active})
            conn.commit()
        finally:
            conn.close()

    def provision_membership(
        self, issuer: str, subject: str, tenant_id: str, scopes,
    ) -> None:
        issuer = _required_text(issuer, "issuer")
        subject = _required_text(subject, "subject")
        tenant_id = _required_text(tenant_id, "tenant_id")
        validated_scopes = _validate_scopes(scopes)
        scopes_json = json.dumps(sorted(validated_scopes), separators=(",", ":"))
        conn = self._connect()
        try:
            tenant = conn.execute(
                "SELECT active FROM tenant_registry WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()
            if tenant is None or not tenant["active"]:
                raise MembershipNotFoundError("Active tenant was not found.")
            conn.execute(
                """INSERT INTO tenant_memberships
                   (issuer, subject, tenant_id, active, scopes_json)
                   VALUES (?, ?, ?, 1, ?)
                   ON CONFLICT(issuer, subject, tenant_id) DO UPDATE SET
                     active = 1, scopes_json = excluded.scopes_json,
                     updated_at = CURRENT_TIMESTAMP""",
                (issuer, subject, tenant_id, scopes_json),
            )
            self._record_audit(conn, "membership.provisioned", tenant_id, issuer, subject,
                               {"scopes": sorted(validated_scopes)})
            conn.commit()
        finally:
            conn.close()

    def revoke_membership(self, issuer: str, subject: str, tenant_id: str) -> bool:
        issuer = _required_text(issuer, "issuer")
        subject = _required_text(subject, "subject")
        tenant_id = _required_text(tenant_id, "tenant_id")
        conn = self._connect()
        try:
            cur = conn.execute(
                """UPDATE tenant_memberships SET active = 0, updated_at = CURRENT_TIMESTAMP
                   WHERE issuer = ? AND subject = ? AND tenant_id = ? AND active = 1""",
                (issuer, subject, tenant_id),
            )
            if cur.rowcount == 1:
                self._record_audit(conn, "membership.revoked", tenant_id, issuer, subject)
            conn.commit()
            return cur.rowcount == 1
        finally:
            conn.close()

    def resolve_membership(
        self, issuer: str, subject: str, tenant_id: Optional[str] = None,
    ) -> MembershipRecord:
        issuer = _required_text(issuer, "issuer")
        subject = _required_text(subject, "subject")
        if tenant_id is not None:
            tenant_id = _required_text(tenant_id, "tenant_id")
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT m.issuer, m.subject, m.tenant_id, m.active,
                          m.scopes_json, t.active AS tenant_active
                   FROM tenant_memberships m
                   JOIN tenant_registry t ON t.tenant_id = m.tenant_id
                   WHERE m.issuer = ? AND m.subject = ?
                   ORDER BY m.tenant_id""",
                (issuer, subject),
            ).fetchall()
            if tenant_id is not None:
                rows = [row for row in rows if row["tenant_id"] == tenant_id]
            active_rows = [row for row in rows if row["active"] and row["tenant_active"]]
            if not active_rows:
                if rows:
                    raise InactiveMembershipError("Active tenant membership required.")
                raise MembershipNotFoundError("Tenant membership was not found.")
            if len(active_rows) != 1:
                raise AmbiguousMembershipError(
                    "Identity has multiple active tenant memberships; select an authorised tenant."
                )
            row = active_rows[0]
            try:
                scopes = _validate_scopes(json.loads(row["scopes_json"]))
            except (TypeError, ValueError, json.JSONDecodeError):
                raise InactiveMembershipError("Stored membership permissions are invalid.") from None
            return MembershipRecord(
                issuer=row["issuer"], subject=row["subject"],
                tenant_id=row["tenant_id"], active=True, scopes=scopes,
            )
        finally:
            conn.close()
