import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

from atlas_engine.oidc_contract import OIDCProviderConfig, VerifiedTokenClaims
from atlas_engine.oidc_jwt_verifier import OIDCVerifierUnavailable, PyJWTTokenVerifier


ISSUER = "https://identity.example.test/"
CONFIG = OIDCProviderConfig(
    issuer=ISSUER,
    audience="atlas-api",
    jwks_uri=ISSUER + ".well-known/jwks.json",
    allowed_algorithms=frozenset({"RS256"}),
    clock_skew_seconds=0,
)
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


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
        "aud": "atlas-api",
        "exp": now + 300,
        "nbf": now - 5,
        "roles": ["atlas_viewer"],
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


def test_verifies_rsa_signature_and_registered_claims():
    token = _token()
    jwks = FakeJWKS(PRIVATE_KEY.public_key())
    claims = PyJWTTokenVerifier(CONFIG, jwks).verify(token)
    assert isinstance(claims, VerifiedTokenClaims)
    assert claims.issuer == ISSUER
    assert claims.subject == "subject-123"
    assert claims.audiences == ("atlas-api",)
    assert claims.roles == ("atlas_viewer",)
    assert jwks.received_token == token


def test_rejects_invalid_signature():
    token = _token(key=OTHER_PRIVATE_KEY)
    verifier = PyJWTTokenVerifier(CONFIG, FakeJWKS(PRIVATE_KEY.public_key()))
    with pytest.raises(ValueError, match="verification failed"):
        verifier.verify(token)


def test_rejects_disallowed_algorithm_even_when_token_is_signed():
    token = _token(algorithm="HS256", key="not-a-trusted-rsa-key")
    verifier = PyJWTTokenVerifier(CONFIG, FakeJWKS(PRIVATE_KEY.public_key()))
    with pytest.raises(ValueError, match="verification failed"):
        verifier.verify(token)


@pytest.mark.parametrize("changes", [
    {"iss": "https://attacker.example/"},
    {"aud": "another-api"},
    {"exp": int(time.time()) - 120},
    {"nbf": int(time.time()) + 120},
    {"sub": ""},
])
def test_rejects_wrong_registered_claims(changes):
    token = _token(_payload(**changes))
    verifier = PyJWTTokenVerifier(CONFIG, FakeJWKS(PRIVATE_KEY.public_key()))
    with pytest.raises(ValueError):
        verifier.verify(token)


def test_requires_explicit_not_before_claim():
    payload = _payload()
    payload.pop("nbf")
    token = _token(payload)
    verifier = PyJWTTokenVerifier(CONFIG, FakeJWKS(PRIVATE_KEY.public_key()))
    with pytest.raises(ValueError, match="verification failed"):
        verifier.verify(token)


def test_rejects_malformed_roles_claim():
    token = _token(_payload(roles="atlas_admin"))
    verifier = PyJWTTokenVerifier(CONFIG, FakeJWKS(PRIVATE_KEY.public_key()))
    with pytest.raises(ValueError, match="claims are malformed"):
        verifier.verify(token)


def test_unknown_signing_key_is_rejected():
    verifier = PyJWTTokenVerifier(CONFIG, FakeJWKS(error=PyJWKClientError("unknown kid")))
    with pytest.raises(ValueError, match="signing key"):
        verifier.verify(_token())


def test_jwks_transport_failure_is_reported_as_unavailable():
    verifier = PyJWTTokenVerifier(
        CONFIG,
        FakeJWKS(error=PyJWKClientConnectionError("private network details")),
    )
    with pytest.raises(OIDCVerifierUnavailable):
        verifier.verify(_token())


def test_oversized_or_empty_token_rejected_before_key_lookup():
    jwks = FakeJWKS(PRIVATE_KEY.public_key())
    verifier = PyJWTTokenVerifier(CONFIG, jwks)
    with pytest.raises(ValueError):
        verifier.verify("")
    with pytest.raises(ValueError):
        verifier.verify("x" * 8193)
    assert jwks.received_token is None


def test_multiple_audiences_require_matching_authorized_party():
    payload = _payload(aud=["atlas-api", "another-api"])
    token = _token(payload)
    verifier = PyJWTTokenVerifier(CONFIG, FakeJWKS(PRIVATE_KEY.public_key()))
    with pytest.raises(ValueError, match="claims are malformed"):
        verifier.verify(token)


def test_multiple_audiences_accept_matching_authorized_party():
    payload = _payload(aud=["atlas-api", "another-api"], azp="atlas-api")
    token = _token(payload)
    verifier = PyJWTTokenVerifier(CONFIG, FakeJWKS(PRIVATE_KEY.public_key()))
    assert verifier.verify(token).audiences == ("atlas-api", "another-api")


def test_mismatched_authorized_party_is_rejected():
    payload = _payload(azp="another-client")
    token = _token(payload)
    verifier = PyJWTTokenVerifier(CONFIG, FakeJWKS(PRIVATE_KEY.public_key()))
    with pytest.raises(ValueError, match="claims are malformed"):
        verifier.verify(token)
