import pytest

from atlas_engine.oidc_composition import principal_from_verified_claims
from atlas_engine.oidc_contract import OIDCConfigurationError, OIDCProviderConfig, VerifiedTokenClaims
from atlas_engine.tenant_membership import MembershipNotFoundError, SQLiteMembershipRegistry


ISSUER = "https://identity.example.test/"
CONFIG = OIDCProviderConfig(
    issuer=ISSUER,
    audience="atlas-api",
    jwks_uri="https://identity.example.test/.well-known/jwks.json",
    allowed_algorithms=frozenset({"RS256"}),
)


@pytest.fixture
def registry(tmp_path):
    store = SQLiteMembershipRegistry(str(tmp_path / "oidc-memberships.sqlite"))
    store.initialize()
    store.create_tenant("tenant-a", "Company A")
    store.provision_membership(ISSUER, "user-1", "tenant-a", {"tasks:read"})
    return store


def claims(**overrides):
    values = {
        "issuer": ISSUER,
        "subject": "user-1",
        "audiences": ("atlas-api",),
        "expires_at": 2_000_000_000,
        "not_before": 1_700_000_000,
        "roles": ("atlas_viewer",),
    }
    values.update(overrides)
    return VerifiedTokenClaims(**values)


def test_verified_claims_resolve_principal_from_server_side_membership(registry):
    principal = principal_from_verified_claims(claims(), CONFIG, registry)
    assert principal.tenant_id == "tenant-a"
    assert principal.scopes == frozenset({"tasks:read"})


def test_provider_roles_do_not_override_membership_scopes(registry):
    principal = principal_from_verified_claims(
        claims(roles=("atlas_operator", "tenant_admin")), CONFIG, registry
    )
    assert principal.scopes == frozenset({"tasks:read"})


def test_unknown_subject_fails_closed(registry):
    with pytest.raises(MembershipNotFoundError):
        principal_from_verified_claims(claims(subject="unknown"), CONFIG, registry)


def test_wrong_audience_fails_before_membership_lookup(registry):
    with pytest.raises(OIDCConfigurationError):
        principal_from_verified_claims(claims(audiences=("other-api",)), CONFIG, registry)


def test_untrusted_mapping_is_not_accepted(registry):
    with pytest.raises(TypeError):
        principal_from_verified_claims({"issuer": ISSUER}, CONFIG, registry)
