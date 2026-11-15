"""Composition of trusted OIDC adapter output with server-side membership.

The TokenVerifier must be the source of VerifiedTokenClaims. This function
rechecks issuer/audience and resolves permissions only from the membership
registry. It does not verify signatures or accept HTTP payloads.
"""
from typing import Optional

from .identity_policy import RequestPrincipal
from .oidc_contract import OIDCProviderConfig, VerifiedTokenClaims, validate_verified_claims
from .tenant_membership import SQLiteMembershipRegistry
from .verified_identity import VerifiedIdentity, principal_from_verified_identity


def principal_from_verified_claims(
    claims: VerifiedTokenClaims,
    config: OIDCProviderConfig,
    registry: SQLiteMembershipRegistry,
    tenant_id: Optional[str] = None,
) -> RequestPrincipal:
    """Resolve an authenticated subject to a tenant principal.

    The caller must obtain claims from a configured TokenVerifier. Provider
    role strings are not permissions; tenant membership scopes in the
    server-controlled registry remain authoritative.
    """
    validate_verified_claims(claims, config)
    return principal_from_verified_identity(
        VerifiedIdentity(issuer=claims.issuer, subject=claims.subject),
        registry,
        tenant_id=tenant_id,
    )
