import pytest

from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.tenant_membership import (
    AmbiguousMembershipError,
    InactiveMembershipError,
    MembershipNotFoundError,
    SQLiteMembershipRegistry,
)
from atlas_engine.verified_identity import (
    VerifiedIdentity,
    principal_from_verified_identity,
)


ISSUER = "https://issuer.example.test/"
SUBJECT = "verified-subject"


@pytest.fixture
def registry(tmp_path):
    store = SQLiteMembershipRegistry(str(tmp_path / "membership.sqlite"))
    store.initialize()
    store.create_tenant("tenant-a", "Company A")
    store.create_tenant("tenant-b", "Company B")
    return store


def test_composition_uses_server_side_membership_and_scopes(registry):
    registry.provision_membership(ISSUER, SUBJECT, "tenant-a", {"tasks:read"})
    principal = principal_from_verified_identity(VerifiedIdentity(ISSUER, SUBJECT), registry)
    assert isinstance(principal, RequestPrincipal)
    assert principal.tenant_id == "tenant-a"
    assert principal.scopes == frozenset({"tasks:read"})


def test_unknown_identity_fails_closed(registry):
    with pytest.raises(MembershipNotFoundError):
        principal_from_verified_identity(VerifiedIdentity(ISSUER, "unknown"), registry)


def test_revoked_membership_fails_closed(registry):
    registry.provision_membership(ISSUER, SUBJECT, "tenant-a", {"tasks:read"})
    registry.revoke_membership(ISSUER, SUBJECT, "tenant-a")
    with pytest.raises(InactiveMembershipError):
        principal_from_verified_identity(VerifiedIdentity(ISSUER, SUBJECT), registry)


def test_ambiguous_membership_fails_without_tenant_selection(registry):
    registry.provision_membership(ISSUER, SUBJECT, "tenant-a", {"tasks:read"})
    registry.provision_membership(ISSUER, SUBJECT, "tenant-b", {"sources:read"})
    with pytest.raises(AmbiguousMembershipError):
        principal_from_verified_identity(VerifiedIdentity(ISSUER, SUBJECT), registry)


def test_tenant_selection_must_match_existing_membership(registry):
    registry.provision_membership(ISSUER, SUBJECT, "tenant-a", {"tasks:read"})
    with pytest.raises(MembershipNotFoundError):
        principal_from_verified_identity(
            VerifiedIdentity(ISSUER, SUBJECT), registry, tenant_id="tenant-b"
        )


def test_arbitrary_payload_is_not_accepted_as_verified_identity(registry):
    with pytest.raises(TypeError):
        principal_from_verified_identity(
            {"issuer": ISSUER, "subject": SUBJECT}, registry
        )
