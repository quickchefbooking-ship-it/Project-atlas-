"""HTTP authentication boundary for Professor.

Supports an explicitly configured OIDC bearer verifier and Atlas-owned opaque
browser sessions. Browser permissions are resolved only through the server-side
membership registry. Cookie requests require exact trusted-origin and CSRF checks
for state-changing methods; bearer authentication remains available for services.
"""
from dataclasses import dataclass
import sqlite3
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
from .oidc_jwt_verifier import OIDCVerifierUnavailable
from .session_identity import InvalidSession

MAX_BEARER_TOKEN_LENGTH = 8192
ATLAS_SESSION_COOKIE = "__Host-atlas_session"
ATLAS_CSRF_HEADER = "X-Atlas-CSRF"
_BEARER_PATTERN = re.compile(r"^Bearer ([A-Za-z0-9._~+/=-]+)$")
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


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
        return principal_from_verified_claims(
            claims, self.config, self.memberships
        )


def _cookie_principal(request: Request, csrf_token: Optional[str]) -> RequestPrincipal:
    """Authenticate an Atlas browser cookie without trusting browser identity data."""
    session_token = getattr(request, "cookies", {}).get(ATLAS_SESSION_COOKIE)
    if not isinstance(session_token, str) or not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Atlas browser authentication required.",
        )
    service = getattr(request.app.state, "atlas_session_identity_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verified user identity is not configured.",
        )

    # Origin is mandatory for unsafe cookie-authenticated requests. Exact
    # scheme/host matching prevents wildcard and suffix-based trust mistakes.
    if request.method.upper() not in _SAFE_METHODS:
        trusted_origins = getattr(request.app.state, "atlas_trusted_origins", frozenset())
        origin = request.headers.get("origin")
        fetch_site = request.headers.get("sec-fetch-site", "").lower()
        if (not isinstance(origin, str) or origin not in trusted_origins
                or fetch_site == "cross-site"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Untrusted request origin.",
            )
        if not service.sessions.validate_csrf_token(session_token, csrf_token or ""):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed.",
            )
    try:
        return service.authenticate(session_token)
    except (sqlite3.Error, OSError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity verification or membership lookup is temporarily unavailable.",
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Atlas browser authentication.",
        ) from None


def require_verified_principal(
    request: Request,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    csrf_token: Optional[str] = Header(default=None, alias=ATLAS_CSRF_HEADER),
) -> RequestPrincipal:
    """FastAPI dependency: bearer token or secure Atlas session cookie."""
    # Explicit bearer credentials retain the existing service-to-service path.
    if isinstance(authorization, str):
        service = getattr(request.app.state, "identity_service", None)
        if not isinstance(service, VerifiedIdentityService):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Verified user identity is not configured.",
            )
        match = _BEARER_PATTERN.fullmatch(authorization) if isinstance(authorization, str) else None
        if not match or len(match.group(1)) > MAX_BEARER_TOKEN_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer authentication.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            return service.authenticate(match.group(1))
        except (IdentityVerifierUnavailable, OIDCVerifierUnavailable, sqlite3.Error):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Identity verification or membership lookup is temporarily unavailable.",
            ) from None
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer authentication.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from None
    if not getattr(request, "cookies", {}).get(ATLAS_SESSION_COOKIE):
        if getattr(request.app.state, "identity_service", None) is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Verified user identity is not configured.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer or Atlas browser authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _cookie_principal(request, csrf_token)
