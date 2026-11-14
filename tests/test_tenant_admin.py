import pytest

from atlas_engine.identity_policy import AuthorizationDenied, RequestPrincipal
from atlas_engine.tenant_admin import provision_tenant_member, revoke_tenant_member
from atlas_engine.tenant_membership import SQLiteMembershipRegistry

ISSUER = "https://issuer.example.test/"
ADMIN = RequestPrincipal(ISSUER, "admin-1", "tenant-a", True, frozenset({"tenant:members:manage"}))


@pytest.fixture
def registry(tmp_path):
    store = SQLiteMembershipRegistry(str(tmp_path / "memberships.sqlite"))
    store.initialize()
    store.create_tenant("tenant-a", "Company A")
    store.create_tenant("tenant-b", "Company B")
    return store


def test_provisioning_requires_membership_admin_scope(registry):
    viewer = RequestPrincipal(ISSUER, "viewer", "tenant-a", True, frozenset({"tasks:read"}))
    with pytest.raises(AuthorizationDenied):
        provision_tenant_member(registry, viewer, ISSUER, "new-user", {"tasks:read"})


def test_provisioning_audits_admin_actor(registry):
    provision_tenant_member(registry, ADMIN, ISSUER, "new-user", {"tasks:read"})
    event = registry.list_audit_events("tenant-a")[-1]
    assert event["event_type"] == "membership.provisioned"
    assert event["actor_issuer"] == ADMIN.issuer
    assert event["actor_subject"] == ADMIN.subject


def test_revocation_audits_admin_actor(registry):
    registry.provision_membership(ISSUER, "member", "tenant-a", {"tasks:read"})
    assert revoke_tenant_member(registry, ADMIN, ISSUER, "member") is True
    event = registry.list_audit_events("tenant-a")[-1]
    assert event["event_type"] == "membership.revoked"
    assert event["actor_issuer"] == ADMIN.issuer
    assert event["actor_subject"] == ADMIN.subject


def test_inactive_admin_is_denied(registry):
    inactive = RequestPrincipal(ISSUER, "admin-1", "tenant-a", False, frozenset({"tenant:members:manage"}))
    with pytest.raises(AuthorizationDenied):
        provision_tenant_member(registry, inactive, ISSUER, "new-user", {"tasks:read"})


def test_membership_admin_cannot_be_forged_from_mapping(registry):
    forged = {"issuer": ISSUER, "subject": "admin", "tenant_id": "tenant-a"}
    with pytest.raises(AuthorizationDenied):
        provision_tenant_member(registry, forged, ISSUER, "new-user", {"tasks:read"})


def test_administration_uses_only_principal_tenant(registry):
    provision_tenant_member(registry, ADMIN, ISSUER, "member-a", {"tasks:read"})
    assert registry.resolve_membership(ISSUER, "member-a").tenant_id == "tenant-a"


def test_registry_rejects_actor_without_admin_scope(registry):
    viewer = RequestPrincipal(ISSUER, "viewer", "tenant-a", True, frozenset({"tasks:read"}))
    with pytest.raises(AuthorizationDenied):
        registry.provision_membership(ISSUER, "new-user", "tenant-a", {"tasks:read"}, _actor=viewer)


def test_registry_rejects_actor_from_another_tenant(registry):
    other_admin = RequestPrincipal(ISSUER, "admin-b", "tenant-b", True, frozenset({"tenant:members:manage"}))
    with pytest.raises(AuthorizationDenied):
        registry.provision_membership(ISSUER, "new-user", "tenant-a", {"tasks:read"}, _actor=other_admin)
