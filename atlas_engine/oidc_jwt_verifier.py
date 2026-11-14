"""Cryptographic JWT verification against a pinned OIDC issuer JWKS endpoint.

Uses PyJWT's maintained JWK client and never follows token-provided key URLs.
The configured issuer, audience, JWKS URL and algorithms are deployment-owned.
"""
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError, PyJWTError

from .oidc_contract import OIDCProviderConfig, VerifiedTokenClaims


class OIDCVerifierUnavailable(RuntimeError):
    """The trusted issuer's signing keys could not be obtained safely."""


class PyJWTTokenVerifier:
    """Verify signed access tokens using a configured issuer JWKS endpoint."""

    def __init__(self, config: OIDCProviderConfig, jwks_client: Any = None):
        self.config = config
        self._jwks_client = jwks_client or PyJWKClient(
            config.jwks_uri,
            cache_jwk_set=True,
            lifespan=300,
            timeout=5,
        )

    def verify(self, bearer_token: str) -> VerifiedTokenClaims:
        if not isinstance(bearer_token, str) or not bearer_token or len(bearer_token) > 8192:
            raise ValueError("Bearer token is missing or exceeds the permitted size.")
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(bearer_token)
        except PyJWKClientError:
            # Do not turn unknown kid / malformed key responses into an outage
            # unless the underlying JWKS transport itself failed.
            raise ValueError("Token signing key was not accepted.") from None
        except Exception as exc:
            # Network/transport errors are surfaced as unavailable, not accepted.
            raise OIDCVerifierUnavailable("Issuer signing keys are unavailable.") from exc

        try:
            decoded = jwt.decode(
                bearer_token,
                signing_key.key,
                algorithms=sorted(self.config.allowed_algorithms),
                audience=self.config.audience,
                issuer=self.config.issuer,
                leeway=self.config.clock_skew_seconds,
                options={
                    "require": ["exp", "nbf", "iss", "sub", "aud"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
        except PyJWTError:
            raise ValueError("Bearer token verification failed.") from None

        issuer = decoded.get("iss")
        subject = decoded.get("sub")
        audience = decoded.get("aud")
        expires_at = decoded.get("exp")
        not_before = decoded.get("nbf")
        roles = decoded.get("roles", ())
        audiences = (audience,) if isinstance(audience, str) else audience
        if (
            not isinstance(issuer, str)
            or not isinstance(subject, str)
            or not subject
            or len(subject) > 512
            or not isinstance(audiences, list) and not isinstance(audiences, tuple)
            or any(not isinstance(item, str) or not item for item in audiences)
            or not isinstance(expires_at, int)
            or isinstance(expires_at, bool)
            or not isinstance(not_before, int)
            or isinstance(not_before, bool)
            or not isinstance(roles, (list, tuple))
            or any(not isinstance(role, str) or not role for role in roles)
        ):
            raise ValueError("Verified token claims are malformed.")
        return VerifiedTokenClaims(
            issuer=issuer,
            subject=subject,
            audiences=tuple(audiences),
            expires_at=expires_at,
            not_before=not_before,
            roles=tuple(roles),
        )
