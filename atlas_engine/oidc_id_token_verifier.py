"""Pinned-JWKS verification for OIDC ID tokens used by hosted login.

ID tokens are not API access tokens. This verifier uses the configured issuer,
JWKS endpoint and algorithm allowlist, but requires the OIDC client ID separately
from the API audience. It returns the nonce only to trusted server code so the
one-time login transaction store can compare it with its keyed nonce digest.
"""
from __future__ import annotations

import base64
import hmac
import math
import re
from dataclasses import dataclass, field
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError, PyJWTError

from .oidc_contract import OIDCProviderConfig
from .oidc_jwt_verifier import OIDCVerifierUnavailable


MAX_ID_TOKEN_LENGTH = 8192
MAX_ACCESS_TOKEN_LENGTH = 8192
_NONCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,256}$")


@dataclass(frozen=True)
class VerifiedIDTokenClaims:
    """Minimal claims from a cryptographically verified OIDC ID token."""

    issuer: str
    subject: str
    audiences: tuple[str, ...]
    expires_at: float
    issued_at: float
    nonce: str = field(repr=False)


class PyJWTIDTokenVerifier:
    """Verify an ID token against one deployment-pinned OIDC issuer.

    config.audience remains the API audience used for bearer-token
    authentication. client_id is deliberately separate because OIDC ID
    tokens are issued to the registered browser client, not to the Atlas API.
    """

    def __init__(
        self,
        config: OIDCProviderConfig,
        client_id: str,
        jwks_client: Any = None,
    ):
        if not isinstance(config, OIDCProviderConfig):
            raise TypeError("A trusted OIDC provider configuration is required.")
        if not isinstance(client_id, str) or not client_id.strip() or len(client_id) > 512:
            raise ValueError("A non-empty OIDC client ID of at most 512 characters is required.")
        self.config = config
        self.client_id = client_id
        self._jwks_client = jwks_client or PyJWKClient(
            config.jwks_uri,
            cache_jwk_set=True,
            lifespan=300,
            timeout=5,
        )

    def verify(
        self,
        id_token: str,
        *,
        access_token: str | None = None,
    ) -> VerifiedIDTokenClaims:
        """Verify signature and required ID-token claims without consuming state.

        The caller must still compare the returned nonce with the consumed
        server-side login transaction using nonce_matches. The raw nonce
        is never included in the dataclass representation.
        """
        if not isinstance(id_token, str) or not id_token or len(id_token) > MAX_ID_TOKEN_LENGTH:
            raise ValueError("OIDC ID token is missing or exceeds the permitted size.")

        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(id_token)
        except PyJWKClientConnectionError as exc:
            raise OIDCVerifierUnavailable("Issuer signing keys are unavailable.") from exc
        except PyJWKClientError:
            raise ValueError("ID-token signing key was not accepted.") from None
        except Exception as exc:
            raise OIDCVerifierUnavailable("Issuer signing keys are unavailable.") from exc

        try:
            decoded = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=sorted(self.config.allowed_algorithms),
                audience=self.client_id,
                issuer=self.config.issuer,
                leeway=self.config.clock_skew_seconds,
                options={
                    "require": ["exp", "iat", "iss", "sub", "aud", "nonce"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_nbf": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
            header = jwt.get_unverified_header(id_token)
        except PyJWTError:
            raise ValueError("OIDC ID-token verification failed.") from None

        issuer = decoded.get("iss")
        subject = decoded.get("sub")
        audience = decoded.get("aud")
        expires_at = decoded.get("exp")
        issued_at = decoded.get("iat")
        nonce = decoded.get("nonce")
        authorized_party = decoded.get("azp")
        audiences = (audience,) if isinstance(audience, str) else audience

        if (
            issuer != self.config.issuer
            or not isinstance(subject, str)
            or not subject
            or len(subject) > 512
            or not isinstance(audiences, (list, tuple))
            or not audiences
            or any(not isinstance(item, str) or not item for item in audiences)
            or not isinstance(expires_at, (int, float))
            or isinstance(expires_at, bool)
            or not math.isfinite(expires_at)
            or not isinstance(issued_at, (int, float))
            or isinstance(issued_at, bool)
            or not math.isfinite(issued_at)
            or not isinstance(nonce, str)
            or not _NONCE_PATTERN.fullmatch(nonce)
            or (authorized_party is not None and authorized_party != self.client_id)
            or (len(audiences) > 1 and authorized_party != self.client_id)
        ):
            raise ValueError("Verified OIDC ID-token claims are malformed.")

        algorithm = header.get("alg")
        if not isinstance(algorithm, str) or algorithm not in self.config.allowed_algorithms:
            raise ValueError("OIDC ID-token signing algorithm is not allowed.")

        at_hash = decoded.get("at_hash")
        if at_hash is not None:
            if (
                not isinstance(at_hash, str)
                or not at_hash
                or len(at_hash) > 256
                or not isinstance(access_token, str)
                or not access_token
                or len(access_token) > MAX_ACCESS_TOKEN_LENGTH
            ):
                raise ValueError("OIDC ID-token access-token hash cannot be validated.")
            try:
                digest = jwt.get_algorithm_by_name(algorithm).compute_hash_digest(access_token)
                expected_at_hash = base64.urlsafe_b64encode(
                    digest[: len(digest) // 2]
                ).rstrip(b"=").decode("ascii")
            except Exception:
                raise ValueError("OIDC ID-token access-token hash cannot be validated.") from None
            if not hmac.compare_digest(at_hash, expected_at_hash):
                raise ValueError("OIDC ID-token access-token hash does not match.")

        return VerifiedIDTokenClaims(
            issuer=issuer,
            subject=subject,
            audiences=tuple(audiences),
            expires_at=float(expires_at),
            issued_at=float(issued_at),
            nonce=nonce,
        )
