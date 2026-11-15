import os

from atlas_engine.http_identity import VerifiedIdentityService
from atlas_engine.oidc_jwt_verifier import PyJWTTokenVerifier
from app import _identity_service_from_environment, _initialize_tenant_data_store


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



def test_tenant_plan_database_cannot_reuse_core_database(monkeypatch, tmp_path):
    from atlas_engine import storage

    core_path = tmp_path / "core.sqlite"
    monkeypatch.setattr(storage, "DB_PATH", str(core_path))
    monkeypatch.setenv("ATLAS_TENANT_DATA_DB_PATH", str(core_path))
    monkeypatch.delenv("ATLAS_MEMBERSHIP_DB_PATH", raising=False)

    import pytest
    with pytest.raises(ValueError, match="separate from core and membership"):
        _initialize_tenant_data_store()


def test_tenant_plan_database_cannot_reuse_membership_database(monkeypatch, tmp_path):
    from atlas_engine import storage
    import pytest

    core_path = tmp_path / "core.sqlite"
    membership_path = tmp_path / "members.sqlite"
    tenant_path = tmp_path / "tenant.sqlite"
    monkeypatch.setattr(storage, "DB_PATH", str(core_path))
    monkeypatch.setenv("ATLAS_MEMBERSHIP_DB_PATH", str(membership_path))
    monkeypatch.setenv("ATLAS_TENANT_DATA_DB_PATH", str(membership_path))

    with pytest.raises(ValueError, match="separate from core and membership"):
        _initialize_tenant_data_store()
