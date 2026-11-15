import pytest

from atlas_engine.oidc_contract import (
    OIDCConfigurationError,
    OIDCProviderConfig,
    VerifiedTokenClaims,
    validate_verified_claims,
)

CONFIG = OIDCProviderConfig(
    issuer="https://identity.example.test/",
    audience="atlas-api",
    jwks_uri="https://identity.example.test/.well-known/jwks.json",
    allowed_algorithms=frozenset({"RS256"}),
)


def test_valid_provider_config_and_verified_claim_contract():
    claims = VerifiedTokenClaims(
        issuer=CONFIG.issuer,
        subject="user-123",
        audiences=("atlas-api",),
        expires_at=2_000_000_000,
        not_before=1_700_000_000,
        roles=("atlas_viewer",),
    )
    validate_verified_claims(claims, CONFIG)


@pytest.mark.parametrize("kwargs", [
    {"issuer": "http://identity.example.test", "audience": "atlas-api", "jwks_uri": "https://identity.example.test/keys", "allowed_algorithms": frozenset({"RS256"})},
    {"issuer": "https://identity.example.test", "audience": "", "jwks_uri": "https://identity.example.test/keys", "allowed_algorithms": frozenset({"RS256"})},
    {"issuer": "https://identity.example.test", "audience": "atlas-api", "jwks_uri": "http://identity.example.test/keys", "allowed_algorithms": frozenset({"RS256"})},
    {"issuer": "https://identity.example.test", "audience": "atlas-api", "jwks_uri": "https://identity.example.test/keys", "allowed_algorithms": frozenset({"none"})},
    {"issuer": "https://identity.example.test", "audience": "atlas-api", "jwks_uri": "https://identity.example.test/keys", "allowed_algorithms": frozenset({"RS256"}), "clock_skew_seconds": 999},
])
def test_unsafe_provider_config_fails_closed(kwargs):
    with pytest.raises(OIDCConfigurationError):
        OIDCProviderConfig(**kwargs)


def test_wrong_issuer_is_rejected_after_adapter_verification():
    claims = VerifiedTokenClaims(CONFIG.issuer + "wrong", "user", ("atlas-api",), 2_000_000_000, 1_700_000_000, ())
    with pytest.raises(OIDCConfigurationError):
        validate_verified_claims(claims, CONFIG)


def test_wrong_audience_is_rejected_after_adapter_verification():
    claims = VerifiedTokenClaims(CONFIG.issuer, "user", ("other-api",), 2_000_000_000, 1_700_000_000, ())
    with pytest.raises(OIDCConfigurationError):
        validate_verified_claims(claims, CONFIG)


def test_raw_dict_is_not_accepted_as_verified_claims():
    with pytest.raises(TypeError):
        validate_verified_claims({"issuer": CONFIG.issuer}, CONFIG)


def test_algorithm_configuration_must_be_explicit_collection():
    with pytest.raises(OIDCConfigurationError):
        OIDCProviderConfig(CONFIG.issuer, CONFIG.audience, CONFIG.jwks_uri, "RS256")
