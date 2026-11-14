"""Provider-neutral OIDC adapter contract; deliberately no JWT implementation.

A production adapter must verify cryptographic and registered claims before it
returns VerifiedTokenClaims. This module validates deployment configuration
and defines the typed interface only; it does not authenticate bearer tokens.
"""
from dataclasses import dataclass
from typing import FrozenSet, Protocol, Tuple


SUPPORTED_ALGORITHMS = frozenset({"RS256", "PS256", "ES256"})


class OIDCConfigurationError(ValueError):
    """OIDC configuration is incomplete or unsafe."""


@dataclass(frozen=True)
class OIDCProviderConfig:
    issuer: str
    audience: str
    jwks_uri: str
    allowed_algorithms: FrozenSet[str]
    clock_skew_seconds: int = 60

    def __post_init__(self):
        if not isinstance(self.issuer, str) or not self.issuer.startswith("https://") or self.issuer.endswith("/"):
            raise OIDCConfigurationError("Issuer must be an exact HTTPS issuer URL without a trailing slash.")
        if not isinstance(self.audience, str) or not self.audience.strip():
            raise OIDCConfigurationError("A non-empty API audience is required.")
        if not isinstance(self.jwks_uri, str) or not self.jwks_uri.startswith("https://"):
            raise OIDCConfigurationError("JWKS URI must use HTTPS.")
        if not self.allowed_algorithms or not self.allowed_algorithms.issubset(SUPPORTED_ALGORITHMS):
            raise OIDCConfigurationError("Explicit supported signing algorithms are required.")
        if not isinstance(self.clock_skew_seconds, int) or not 0 <= self.clock_skew_seconds <= 300:
            raise OIDCConfigurationError("Clock skew must be an integer between 0 and 300 seconds.")


@dataclass(frozen=True)
class VerifiedTokenClaims:
    """Minimal post-verification claims; never accept this object from HTTP input."""
    issuer: str
    subject: str
    audiences: Tuple[str, ...]
    expires_at: int
    not_before: int
    roles: Tuple[str, ...]


class TokenVerifier(Protocol):
    """Contract implemented by a future audited cryptographic OIDC adapter."""

    def verify(self, bearer_token: str) -> VerifiedTokenClaims:
        """Verify signature, algorithm, issuer, audience, exp, nbf and API intent."""
        ...


def validate_verified_claims(
    claims: VerifiedTokenClaims,
    config: OIDCProviderConfig,
) -> None:
    """Re-check the adapter output contract before membership composition.

    This is defence in depth, not signature verification. The caller must
    still obtain claims from a trusted TokenVerifier implementation.
    """
    if not isinstance(claims, VerifiedTokenClaims):
        raise TypeError("VerifiedTokenClaims from the trusted verifier are required.")
    if claims.issuer != config.issuer:
        raise OIDCConfigurationError("Verified token issuer does not match configured issuer.")
    if config.audience not in claims.audiences:
        raise OIDCConfigurationError("Verified token is not intended for this API audience.")
    if not claims.subject or len(claims.subject) > 512:
        raise OIDCConfigurationError("Verified token subject is missing or invalid.")
    if not claims.audiences or any(not isinstance(item, str) or not item for item in claims.audiences):
        raise OIDCConfigurationError("Verified token audiences are malformed.")
    if not isinstance(claims.expires_at, int) or not isinstance(claims.not_before, int):
        raise OIDCConfigurationError("Verified token time claims must be integer timestamps.")
    if not isinstance(claims.roles, tuple) or any(not isinstance(role, str) or not role for role in claims.roles):
        raise OIDCConfigurationError("Verified provider roles must be a tuple of non-empty strings.")
