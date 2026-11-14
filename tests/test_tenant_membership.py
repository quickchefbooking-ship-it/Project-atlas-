import pytest

from atlas_engine.tenant_membership import (
    AmbiguousMembershipError,
    InactiveMembershipError,
    MembershipNotFoundError,
    SQLiteMembershipRegistry,
)


ISSUER = "https://issuer.example.test/"
SUBJECT = "subject-123"


@pytest.fixture
def registry(tmp_path):
    store = SQLiteMembershipRegistry(str(tmp_path / "memberships.sqlite"))
    store.initialize()
    store.create_tenant("tenant-a", "Company A")
    store.create_tenant("tenant-b", "Company B")
    return store


def test_resolves_only_server_provisioned_membership_and_scopes(registry):
    registry.provision_membership(ISSUER, SUBJECT, "tenant-a", {"tasks:read", "lessons:review"})
    record = registry.resolve_membership(ISSUER, SUBJECT)
    assert record.tenant_id == "tenant-a"
    assert record.active is True
    assert record.scopes == frozenset({"tasks:read", "lessons:review"})


def test_unknown_identity_has_no_membership(registry):
    with pytest.raises(MembershipNotFoundError):
        registry.resolve_membership(ISSUER, "unknown")


def test_revoked_membership_is_denied(registry):
    registry.provision_membership(ISSUER, SUBJECT, "tenant-a", {"tasks:read"})
    assert registry.revoke_membership(ISSUER, SUBJECT, "tenant-a") is True
    with pytest.raises(InactiveMembershipError):
        registry.resolve_membership(ISSUER, SUBJECT)


def test_multiple_active_tenants_are_ambiguous_without_selection(registry):
    registry.provision_membership(ISSUER, SUBJECT, "tenant-a", {"tasks:read"})
    registry.provision_membership(ISSUER, SUBJECT, "tenant-b", {"sources:read"})
    with pytest.raises(AmbiguousMembershipError):
        registry.resolve_membership(ISSUER, SUBJECT)


def test_explicit_membership_selection_is_resolved_against_registry(registry):
    registry.provision_membership(ISSUER, SUBJECT, "tenant-a", {"tasks:read"})
    registry.provision_membership(ISSUER, SUBJECT, "tenant-b", {"sources:read"})
    record = registry.resolve_membership(ISSUER, SUBJECT, "tenant-b")
    assert record.tenant_id == "tenant-b"
    assert record.scopes == frozenset({"sources:read"})


def test_inactive_tenant_cannot_be_resolved(registry):
    registry.provision_membership(ISSUER, SUBJECT, "tenant-a", {"tasks:read"})
    registry.set_tenant_active("tenant-a", False)
    with pytest.raises(InactiveMembershipError):
        registry.resolve_membership(ISSUER, SUBJECT)


def test_membership_cannot_be_provisioned_for_unknown_or_inactive_tenant(registry):
    with pytest.raises(MembershipNotFoundError):
        registry.provision_membership(ISSUER, SUBJECT, "missing", {"tasks:read"})
    registry.set_tenant_active("tenant-a", False)
    with pytest.raises(MembershipNotFoundError):
        registry.provision_membership(ISSUER, SUBJECT, "tenant-a", {"tasks:read"})


@pytest.mark.parametrize("scopes", ["tasks:read", b"tasks:read", [None], [""]])
def test_invalid_scope_provisioning_is_rejected(registry, scopes):
    with pytest.raises(ValueError):
        registry.provision_membership(ISSUER, SUBJECT, "tenant-a", scopes)


def test_reprovisioning_updates_scopes_and_reactivates_membership(registry):
    registry.provision_membership(ISSUER, SUBJECT, "tenant-a", {"tasks:read"})
    registry.revoke_membership(ISSUER, SUBJECT, "tenant-a")
    registry.provision_membership(ISSUER, SUBJECT, "tenant-a", {"tasks:write"})
    record = registry.resolve_membership(ISSUER, SUBJECT)
    assert record.scopes == frozenset({"tasks:write"})


def test_membership_mutations_append_audit_events(registry):
    registry.provision_membership(ISSUER, SUBJECT, "tenant-a", {"tasks:read", "lessons:review"})
    registry.revoke_membership(ISSUER, SUBJECT, "tenant-a")
    events = registry.list_audit_events("tenant-a")
    assert [event["event_type"] for event in events] == [
        "tenant.created", "membership.provisioned", "membership.revoked"
    ]
    assert events[1]["issuer"] == ISSUER
    assert events[1]["subject"] == SUBJECT
    assert events[1]["details"] == {"scopes": ["lessons:review", "tasks:read"]}


def test_tenant_deactivation_is_audited(registry):
    registry.set_tenant_active("tenant-a", False)
    event = registry.list_audit_events("tenant-a")[-1]
    assert event["event_type"] == "tenant.deactivated"
    assert event["details"] == {"active": False}


def test_audit_actor_is_not_fabricated_before_verified_admin_auth(registry):
    event = registry.list_audit_events("tenant-a")[0]
    assert event["actor_issuer"] is None
    assert event["actor_subject"] is None


def test_failed_mutation_does_not_create_audit_event(registry):
    before = len(registry.list_audit_events("tenant-a"))
    with pytest.raises(MembershipNotFoundError):
        registry.provision_membership(ISSUER, SUBJECT, "missing", {"tasks:read"})
    assert len(registry.list_audit_events("tenant-a")) == before
