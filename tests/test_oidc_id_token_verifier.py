import base64
import hashlib
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

from atlas_engine.oidc_contract import OIDCProviderConfig
from atlas_engine.oidc_id_token_verifier import (
    MAX_ID_TOKEN_LENGTH,
    PyJWTIDTokenVerifier,
    VerifiedIDTokenClaims,
)
from atlas_engine.oidc_jwt_verifier import OIDCVerifierUnavailable


ISSUER = "https://identity.example.test/"
CLIENT_ID = "atlas-browser-client"
API_CONFIG = OIDCProviderConfig(
    issuer=ISSUER,
    audience="atlas-api",
    jwks_uri=ISSUER + ".well-known/jwks.json",
    allowed_algorithms=frozenset({"RS256"}),
    clock_skew_seconds=0,
)
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
NONCE = "n" * 43


class FakeJWKS:
    def __init__(self, key=None, error=None):
        self.key = key
        self.error = error
        self.received_token = None

    def get_signing_key_from_jwt(self, token):
        self.received_token = token
        if self.error:
            raise self.error
        return SimpleNamespace(key=self.key)


def _payload(**overrides):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "sub": "subject-123",
        "aud": CLIENT_ID,
        "exp": now + 300,
        "iat": now,
        "nonce": NONCE,
    }
    claims.update(overrides)
    return claims


def _token(payload=None, key=PRIVATE_KEY, algorithm="RS256"):
    return jwt.encode(
        _payload() if payload is None else payload,
        key,
        algorithm=algorithm,
        headers={"kid": "trusted-key"},
    )


def _verifier(jwks=None):
    return PyJWTIDTokenVerifier(
        API_CONFIG,
        CLIENT_ID,
        jwks or FakeJWKS(PRIVATE_KEY.public_key()),
    )


def test_verifies_id_token_with_client_id_separate_from_api_audience():
    token = _token()
    jwks = FakeJWKS(PRIVATE_KEY.public_key())

    claims = PyJWTIDTokenVerifier(API_CONFIG, CLIENT_ID, jwks).verify(token)

    assert isinstance(claims, VerifiedIDTokenClaims)
    assert claims.issuer == ISSUER
    assert claims.subject == "subject-123"
    assert claims.audiences == (CLIENT_ID,)
    assert claims.nonce == NONCE
    assert NONCE not in repr(claims)
    assert jwks.received_token == token


def test_rejects_invalid_signature():
    verifier = _verifier(FakeJWKS(PRIVATE_KEY.public_key()))
    with pytest.raises(ValueError, match="verification failed"):
        verifier.verify(_token(key=OTHER_PRIVATE_KEY))


@pytest.mark.parametrize("changes", [
    {"iss": "https://attacker.example/"},
    {"aud": "another-client"},
    {"exp": int(time.time()) - 120},
    {"iat": int(time.time()) + 120},
    {"sub": ""},
    {"nonce": ""},
    {"nonce": "too-short"},
])
def test_rejects_invalid_registered_or_nonce_claims(changes):
    with pytest.raises(ValueError):
        _verifier().verify(_token(_payload(**changes)))


def test_requires_issued_at_and_nonce_claims():
    payload = _payload()
    payload.pop("iat")
    with pytest.raises(ValueError, match="verification failed"):
        _verifier().verify(_token(payload))

    payload = _payload()
    payload.pop("nonce")
    with pytest.raises(ValueError, match="verification failed"):
        _verifier().verify(_token(payload))


def test_multiple_audiences_require_matching_authorized_party():
    payload = _payload(aud=[CLIENT_ID, "another-client"])
    with pytest.raises(ValueError, match="malformed"):
        _verifier().verify(_token(payload))

    payload["azp"] = CLIENT_ID
    assert _verifier().verify(_token(payload)).audiences == (CLIENT_ID, "another-client")


def test_mismatched_authorized_party_is_rejected():
    payload = _payload(azp="another-client")
    with pytest.raises(ValueError, match="malformed"):
        _verifier().verify(_token(payload))


def test_disallowed_signing_algorithm_is_rejected():
    token = _token(_payload(), key="not-a-trusted-key", algorithm="HS256")
    with pytest.raises(ValueError):
        _verifier().verify(token)


def test_valid_at_hash_is_checked_when_present():
    access_token = "atlas-access-token"
    digest = hashlib.sha256(access_token.encode("ascii")).digest()
    at_hash = base64.urlsafe_b64encode(digest[: len(digest) // 2]).rstrip(b"=").decode("ascii")
    token = _token(_payload(at_hash=at_hash))

    assert _verifier().verify(token, access_token=access_token).subject == "subject-123"


@pytest.mark.parametrize("access_token", [None, "", "wrong-access-token"])
def test_at_hash_requires_and_matches_the_token_endpoint_access_token(access_token):
    payload = _payload(at_hash="A" * 22)
    with pytest.raises(ValueError, match="hash"):
        _verifier().verify(_token(payload), access_token=access_token)


def test_jwks_transport_failure_is_reported_as_unavailable():
    verifier = _verifier(FakeJWKS(error=PyJWKClientConnectionError("private transport detail")))
    with pytest.raises(OIDCVerifierUnavailable):
        verifier.verify(_token())


def test_unknown_signing_key_is_rejected():
    verifier = _verifier(FakeJWKS(error=PyJWKClientError("unknown kid")))
    with pytest.raises(ValueError, match="signing key"):
        verifier.verify(_token())


def test_oversized_or_empty_id_token_is_rejected_before_key_lookup():
    jwks = FakeJWKS(PRIVATE_KEY.public_key())
    verifier = _verifier(jwks)
    with pytest.raises(ValueError):
        verifier.verify("")
    with pytest.raises(ValueError):
        verifier.verify("x" * (MAX_ID_TOKEN_LENGTH + 1))
    assert jwks.received_token is None


def test_id_token_client_id_is_required_and_not_confused_with_api_audience():
    with pytest.raises(ValueError):
        PyJWTIDTokenVerifier(API_CONFIG, " ")
    with pytest.raises(ValueError):
        PyJWTIDTokenVerifier(API_CONFIG, "x" * 513)
