import sqlite3
import time

import pytest

from atlas_engine.account_identity import Argon2idCredentialHasher, SQLiteAccountRepository
from atlas_engine.atlas_session_identity import ATLAS_IDENTITY_ISSUER, AtlasSessionIdentityService
from atlas_engine.oidc_account_link import (
    IDENTITY_LINK_SCOPE,
    InactiveAtlasAccount,
    OIDCAccountLinkNotFound,
    OIDCAccountLinkService,
    SQLiteOIDCAccountLinkRepository,
)
from atlas_engine.oidc_id_token_verifier import VerifiedIDTokenClaims
from atlas_engine.oidc_login_session import OIDCLoginSessionService
from atlas_engine.oidc_login_transaction import SQLiteOIDCLoginTransactionStore
from atlas_engine.session_identity import InvalidSession, SQLiteSessionRepository
from atlas_engine.tenant_membership import (
    AmbiguousMembershipError,
    InactiveMembershipError,
    SQLiteMembershipRegistry,
)


ISSUER = "https://idp.example.test/"
CLIENT_ID = "atlas-browser-client"
KEY = b"oidc-login-session-test-key-32!!"


def _attempt(transactions, *, subject="provider-subject", issuer=ISSUER):
    start = transactions.begin()
    consumed = transactions.consume(start.state)
    claims = VerifiedIDTokenClaims(
        issuer=issuer,
        subject=subject,
        audiences=(CLIENT_ID,),
        expires_at=time.time() + 300,
        issued_at=time.time(),
        nonce=start.nonce,
    )
    return claims, consumed


def _session_count(database, *, active_only=False):
    conn = sqlite3.connect(database)
    try:
        query = "SELECT count(*) FROM atlas_sessions"
        if active_only:
            query += " WHERE revoked_at IS NULL AND rotated_to_session_id IS NULL"
        return conn.execute(query).fetchone()[0]
    finally:
        conn.close()


@pytest.fixture
def setup(tmp_path):
    database = str(tmp_path / "atlas-identity.sqlite")
    accounts = SQLiteAccountRepository(
        database,
        Argon2idCredentialHasher(time_cost=1, memory_cost=19456, parallelism=1),
    )
    accounts.initialize()
    account = accounts.create_pending_account(
        "alice@example.test", "a sufficiently long account password"
    )
    accounts.set_account_status(account.account_id, "active")

    sessions = SQLiteSessionRepository(database)
    sessions.initialize()

    memberships = SQLiteMembershipRegistry(str(tmp_path / "memberships.sqlite"))
    memberships.initialize()
    memberships.create_tenant("tenant-a", "Tenant A")
    memberships.provision_membership(
        ATLAS_IDENTITY_ISSUER,
        account.account_id,
        "tenant-a",
        {IDENTITY_LINK_SCOPE, "professor:chat"},
    )

    atlas_identity = AtlasSessionIdentityService(sessions, memberships)
    linking_session = sessions.issue_session(account.account_id)
    linking_principal = atlas_identity.authenticate(linking_session.token)

    links = SQLiteOIDCAccountLinkRepository(accounts)
    links.initialize()
    transactions = SQLiteOIDCLoginTransactionStore(
        str(tmp_path / "login-transactions.sqlite"),
        KEY,
    )
    transactions.initialize()
    account_link_service = OIDCAccountLinkService(links, transactions)

    link_claims, link_transaction = _attempt(transactions)
    account_link_service.link_authenticated_account(
        linking_principal, link_claims, link_transaction
    )

    login_service = OIDCLoginSessionService(
        account_link_service,
        sessions,
        memberships,
    )
    return {
        "account": account,
        "accounts": accounts,
        "sessions": sessions,
        "memberships": memberships,
        "transactions": transactions,
        "account_links": account_link_service,
        "login": login_service,
        "database": database,
    }


def test_complete_login_issues_opaque_session_and_session_bound_csrf(setup):
    claims, transaction = _attempt(setup["transactions"])

    issued = setup["login"].complete_login(claims, transaction)

    assert issued.principal.issuer == ATLAS_IDENTITY_ISSUER
    assert issued.principal.subject == setup["account"].account_id
    assert issued.principal.tenant_id == "tenant-a"
    assert issued.principal.scopes == frozenset({"professor:chat", IDENTITY_LINK_SCOPE})
    assert setup["sessions"].validate_session(issued.session.token).account_id == setup["account"].account_id
    assert setup["sessions"].validate_csrf_token(
        issued.session.token, issued.csrf_token
    ) is True

    other_session = setup["sessions"].issue_session(setup["account"].account_id)
    assert setup["sessions"].validate_csrf_token(
        other_session.token, issued.csrf_token
    ) is False


def test_unknown_external_identity_does_not_issue_an_atlas_session(setup):
    before = _session_count(setup["database"], active_only=True)
    claims, transaction = _attempt(
        setup["transactions"], subject="not-explicitly-linked"
    )

    with pytest.raises(OIDCAccountLinkNotFound):
        setup["login"].complete_login(claims, transaction)

    assert _session_count(setup["database"], active_only=True) == before


def test_inactive_membership_blocks_login_before_session_issuance(setup):
    memberships = setup["memberships"]
    account_id = setup["account"].account_id
    assert memberships.revoke_membership(
        ATLAS_IDENTITY_ISSUER, account_id, "tenant-a"
    )
    before = _session_count(setup["database"], active_only=True)
    claims, transaction = _attempt(setup["transactions"])

    with pytest.raises(InactiveMembershipError):
        setup["login"].complete_login(claims, transaction)

    assert _session_count(setup["database"], active_only=True) == before


def test_ambiguous_active_tenant_memberships_block_login(setup):
    memberships = setup["memberships"]
    account_id = setup["account"].account_id
    memberships.create_tenant("tenant-b", "Tenant B")
    memberships.provision_membership(
        ATLAS_IDENTITY_ISSUER,
        account_id,
        "tenant-b",
        {"professor:chat"},
    )
    before = _session_count(setup["database"], active_only=True)
    claims, transaction = _attempt(setup["transactions"])

    with pytest.raises(AmbiguousMembershipError):
        setup["login"].complete_login(claims, transaction)

    assert _session_count(setup["database"], active_only=True) == before


def test_suspended_atlas_account_cannot_receive_an_oidc_session(setup):
    before = _session_count(setup["database"])
    setup["accounts"].set_account_status(
        setup["account"].account_id, "suspended"
    )
    claims, transaction = _attempt(setup["transactions"])

    with pytest.raises(InactiveAtlasAccount):
        setup["login"].complete_login(claims, transaction)

    assert _session_count(setup["database"]) == before


def test_membership_revoked_during_issuance_causes_new_session_to_be_revoked(
    setup, monkeypatch
):
    sessions = setup["sessions"]
    original_issue = sessions.issue_session
    issued_tokens = []

    def issue_then_revoke_membership(account_id):
        issued = original_issue(account_id)
        issued_tokens.append(issued.token)
        setup["memberships"].revoke_membership(
            ATLAS_IDENTITY_ISSUER, account_id, "tenant-a"
        )
        return issued

    monkeypatch.setattr(sessions, "issue_session", issue_then_revoke_membership)
    claims, transaction = _attempt(setup["transactions"])

    with pytest.raises(InactiveMembershipError):
        setup["login"].complete_login(claims, transaction)

    assert len(issued_tokens) == 1
    with pytest.raises(InvalidSession):
        sessions.validate_session(issued_tokens[0])


def test_csrf_issuance_failure_revokes_the_incomplete_browser_session(
    setup, monkeypatch
):
    sessions = setup["sessions"]
    original_issue = sessions.issue_session
    issued_tokens = []

    def capture_issue(account_id):
        issued = original_issue(account_id)
        issued_tokens.append(issued.token)
        return issued

    def fail_csrf(_session_token):
        raise RuntimeError("simulated CSRF storage failure")

    monkeypatch.setattr(sessions, "issue_session", capture_issue)
    monkeypatch.setattr(sessions, "issue_csrf_token", fail_csrf)
    claims, transaction = _attempt(setup["transactions"])

    with pytest.raises(RuntimeError, match="CSRF storage failure"):
        setup["login"].complete_login(claims, transaction)

    assert len(issued_tokens) == 1
    with pytest.raises(InvalidSession):
        sessions.validate_session(issued_tokens[0])


def test_issued_browser_session_repr_redacts_session_and_csrf_credentials(setup):
    claims, transaction = _attempt(setup["transactions"])
    issued = setup["login"].complete_login(claims, transaction)

    rendered = repr(issued)
    assert issued.session.token not in rendered
    assert issued.csrf_token not in rendered


def test_login_session_service_requires_shared_account_and_session_database(
    setup, tmp_path
):
    separate_sessions = SQLiteSessionRepository(
        str(tmp_path / "separate-sessions.sqlite")
    )

    with pytest.raises(ValueError, match="share the account database"):
        OIDCLoginSessionService(
            setup["account_links"],
            separate_sessions,
            setup["memberships"],
        )
