import os

from atlas_engine.http_identity import VerifiedIdentityService
from atlas_engine.oidc_jwt_verifier import PyJWTTokenVerifier
from app import _identity_service_from_environment


def _clear_identity_environment(monkeypatch):
    for name in (
        "ATLAS_OIDC_ISSUER",
        "ATLAS_OIDC_AUDIENCE",
        "ATLAS_OIDC_JWKS_URI",
        "ATLAS_OIDC_ALLOWED_ALGORITHMS",
        "ATLAS_MEMBERSHIP_DB_PATH",
    ):
        monkeypatch.delenv(name, raising=False)


def test_identity_service_stays_disabled_without_complete_configuration(monkeypatch):
    _clear_identity_environment(monkeypatch)
    monkeypatch.setenv("ATLAS_OIDC_ISSUER", "https://identity.example.test/")
    assert _identity_service_from_environment() is None


def test_complete_server_configuration_builds_verifier_and_membership_store(monkeypatch, tmp_path):
    _clear_identity_environment(monkeypatch)
    monkeypatch.setenv("ATLAS_OIDC_ISSUER", "https://identity.example.test/")
    monkeypatch.setenv("ATLAS_OIDC_AUDIENCE", "atlas-api")
    monkeypatch.setenv("ATLAS_OIDC_JWKS_URI", "https://identity.example.test/keys")
    monkeypatch.setenv("ATLAS_OIDC_ALLOWED_ALGORITHMS", "RS256")
    monkeypatch.setenv("ATLAS_MEMBERSHIP_DB_PATH", str(tmp_path / "membership.sqlite"))

    service = _identity_service_from_environment()
    assert isinstance(service, VerifiedIdentityService)
    assert isinstance(service.verifier, PyJWTTokenVerifier)
    assert service.config.issuer == "https://identity.example.test/"
    assert os.path.exists(str(tmp_path / "membership.sqlite"))
