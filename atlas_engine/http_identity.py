"""HTTP bearer authentication boundary for Professor.

No verifier is configured by default. A deployment must explicitly install an
audited TokenVerifier and provider configuration on app.state.identity_service.
Raw tokens are never logged or returned. Client tenant/role/scope fields are
never read; membership and permissions come only from the server registry.
"""
from dataclasses import dataclass
import re
import time
from typing import Optional

from fastapi import Header, HTTPException, Request, status

from .identity_policy import RequestPrincipal
from .oidc_composition import principal_from_verified_claims
from .oidc_contract import (
    OIDCProviderConfig,
    TokenVerifier,
    validate_verified_claims,
)
from .tenant_membership import SQLiteMembershipRegistry

MAX_BEARER_TOKEN_LENGTH = 8192
_BEARER_PATTERN = re.compile(r"^Bearer ([A-Za-z0-9._~+/=-]+)$")


class IdentityVerifierUnavailable(RuntimeError):
    """The configured verifier cannot safely complete authentication."""


@dataclass(frozen=True)
class VerifiedIdentityService:
    """Server-owned composition of verifier, provider policy and membership."""

    config: OIDCProviderConfig
    verifier: TokenVerifier
    memberships: SQLiteMembershipRegistry

    def authenticate(self, token: str) -> RequestPrincipal:
        claims = self.verifier.verify(token)
        validate_verified_claims(claims, self.config)
        now = int(time.time())
        skew = self.config.clock_skew_seconds
        if claims.expires_at <= now - skew:
            raise ValueError("Token has expired.")
        if claims.not_before > now + skew:
            raise ValueError("Token is not yet valid.")
        # No tenant selector is accepted here. Multiple active memberships
        # are intentionally rejected rather than selecting a tenant by guess.
        return principal_from_verified_claims(
            claims, self.config, self.memberships
        )


def require_verified_principal(
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> RequestPrincipal:
    """FastAPI dependency: bearer token -> verifier -> membership -> principal."""
    service = getattr(request.app.state, "identity_service", None)
    if not isinstance(service, VerifiedIdentityService):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verified user identity is not configured.",
        )
    if not isinstance(authorization, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    match = _BEARER_PATTERN.fullmatch(authorization)
    if not match or len(match.group(1)) > MAX_BEARER_TOKEN_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer authentication.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return service.authenticate(match.group(1))
    except IdentityVerifierUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity verification is temporarily unavailable.",
        ) from None
    except Exception:
        # Do not leak signature, issuer, membership or token parsing details.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer authentication.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
