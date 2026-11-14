"""Composition boundary for an identity verified by a trusted auth adapter.

This module does not validate JWTs. Its input must be created exclusively by
server-side token-verification code after signature, issuer, audience, expiry,
not-before and API-intent checks. Never construct it from request data.
"""
from dataclasses import dataclass
from typing import Optional

from .identity_policy import RequestPrincipal
from .tenant_membership import SQLiteMembershipRegistry


@dataclass(frozen=True)
class VerifiedIdentity:
    """Minimal verified OIDC identity output; not a raw token or claims bag."""

    issuer: str
    subject: str


def principal_from_verified_identity(
    identity: VerifiedIdentity,
    registry: SQLiteMembershipRegistry,
    tenant_id: Optional[str] = None,
) -> RequestPrincipal:
    """Resolve server-side membership and build the immutable request principal.

    Trust boundary: callers must supply VerifiedIdentity only from a trusted
    verifier. This function is not proof that the identity was authenticated.
    """
    if not isinstance(identity, VerifiedIdentity):
        raise TypeError("Trusted VerifiedIdentity output is required.")
    membership = registry.resolve_membership(
        identity.issuer, identity.subject, tenant_id=tenant_id
    )
    return RequestPrincipal(
        issuer=membership.issuer,
        subject=membership.subject,
        tenant_id=membership.tenant_id,
        membership_active=membership.active,
        scopes=membership.scopes,
    )
