import pytest

from atlas_engine.account_identity import SQLiteAccountRepository
from atlas_engine.atlas_session_identity import (
    ATLAS_IDENTITY_ISSUER,
    AtlasSessionIdentityService,
)
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.session_identity import InvalidSession, SQLiteSessionRepository
from atlas_engine.tenant_membership import (
    AmbiguousMembershipError,
    InactiveMembershipError,
    MembershipNotFoundError,
    SQLiteMembershipRegistry,
)


@pytest.fixture
def atlas_identity(tmp_path):
    identity_path = str(tmp_path / "atlas-identity.sqlite")
    accounts = SQLiteAccountRepository(identity_path)
    accounts.initialize()
    account = accounts.create_pending_account(
        "professor@example.test", "a sufficiently long password"
    )
    accounts.set_account_status(account.account_id, "active")
    sessions = SQLiteSessionRepository(identity_path)
    sessions.initialize()
    membership = SQLiteMembershipRegistry(str(tmp_path / "memberships.sqlite"))
    membership.initialize()
    membership.create_tenant("company-a", "Company A")
    service = AtlasSessionIdentityService(sessions, membership)
    return account, sessions, membership, service


def test_live_atlas_session_resolves_only_server_provisioned_membership(atlas_identity):
    account, sessions, memberships, service = atlas_identity
    memberships.provision_membership(
        ATLAS_IDENTITY_ISSUER, account.account_id, "company-a",
        {"professor:chat", "memory:read"},
    )
    issued = sessions.issue_session(account.account_id)
    principal = service.authenticate(issued.token)
    assert isinstance(principal, RequestPrincipal)
    assert principal.issuer == ATLAS_IDENTITY_ISSUER
    assert principal.subject == account.account_id
    assert principal.tenant_id == "company-a"
    assert principal.scopes == frozenset({"professor:chat", "memory:read"})


def test_valid_session_without_membership_fails_closed(atlas_identity):
    account, sessions, _, service = atlas_identity
    issued = sessions.issue_session(account.account_id)
    with pytest.raises(MembershipNotFoundError):
        service.authenticate(issued.token)


def test_revoked_membership_denies_valid_session(atlas_identity):
    account, sessions, memberships, service = atlas_identity
    memberships.provision_membership(
        ATLAS_IDENTITY_ISSUER, account.account_id, "company-a", {"professor:chat"}
    )
    memberships.revoke_membership(
        ATLAS_IDENTITY_ISSUER, account.account_id, "company-a"
    )
    issued = sessions.issue_session(account.account_id)
    with pytest.raises(InactiveMembershipError):
        service.authenticate(issued.token)


def test_multiple_active_tenants_are_not_selected_implicitly(atlas_identity):
    account, sessions, memberships, service = atlas_identity
    memberships.create_tenant("company-b", "Company B")
    for tenant in ("company-a", "company-b"):
        memberships.provision_membership(
            ATLAS_IDENTITY_ISSUER, account.account_id, tenant, {"professor:chat"}
        )
    issued = sessions.issue_session(account.account_id)
    with pytest.raises(AmbiguousMembershipError):
        service.authenticate(issued.token)


def test_revoked_session_denied_even_when_membership_is_active(atlas_identity):
    account, sessions, memberships, service = atlas_identity
    memberships.provision_membership(
        ATLAS_IDENTITY_ISSUER, account.account_id, "company-a", {"professor:chat"}
    )
    issued = sessions.issue_session(account.account_id)
    sessions.revoke_session(issued.token)
    with pytest.raises(InvalidSession):
        service.authenticate(issued.token)
