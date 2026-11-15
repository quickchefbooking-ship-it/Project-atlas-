"""Atlas-owned browser-session to tenant-principal composition.

A valid opaque session authenticates an Atlas account. Authorization is then
resolved independently from the server-controlled tenant membership registry.
No tenant, role, or scope is accepted from browser input.
"""
from dataclasses import dataclass

from .identity_policy import RequestPrincipal
from .session_identity import SQLiteSessionRepository
from .tenant_membership import SQLiteMembershipRegistry
from .verified_identity import VerifiedIdentity, principal_from_verified_identity


ATLAS_IDENTITY_ISSUER = "atlas://identity"


@dataclass(frozen=True)
class AtlasSessionIdentityService:
    """Resolve a live Atlas session into an explicitly provisioned principal."""

    sessions: SQLiteSessionRepository
    memberships: SQLiteMembershipRegistry

    def authenticate(self, session_token: str) -> RequestPrincipal:
        if not isinstance(self.sessions, SQLiteSessionRepository):
            raise TypeError("A trusted Atlas session repository is required.")
        if not isinstance(self.memberships, SQLiteMembershipRegistry):
            raise TypeError("A trusted tenant membership registry is required.")
        session = self.sessions.validate_session(session_token)
        # Account ID is the stable subject; it is never supplied by the client.
        # Tenant and scopes are resolved only by the membership registry.
        return principal_from_verified_identity(
            VerifiedIdentity(
                issuer=ATLAS_IDENTITY_ISSUER,
                subject=session.account_id,
            ),
            self.memberships,
        )
