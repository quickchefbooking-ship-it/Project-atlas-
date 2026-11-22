import sqlite3
import time

import pytest

from atlas_engine.account_identity import Argon2idCredentialHasher, SQLiteAccountRepository
from atlas_engine.atlas_session_identity import ATLAS_IDENTITY_ISSUER, AtlasSessionIdentityService
from atlas_engine.oidc_account_link import (
    IDENTITY_LINK_SCOPE,
    OIDCAccountLinkNotFound,
    OIDCAccountLinkService,
    SQLiteOIDCAccountLinkRepository,
)
from atlas_engine.oidc_browser_login import (
    OIDCBrowserLoginError,
    OIDCBrowserLoginService,
    OIDCTokenResponse,
)
from atlas_engine.oidc_id_token_verifier import VerifiedIDTokenClaims
from atlas_engine.oidc_login_session import OIDCLoginSessionService
from atlas_engine.oidc_login_transaction import (
    InvalidLoginTransaction,
    SQLiteOIDCLoginTransactionStore,
)
from atlas_engine.session_identity import SQLiteSessionRepository
from atlas_engine.tenant_membership import SQLiteMembershipRegistry


ISSUER = "https://idp.example.test/"
CLIENT_ID = "atlas-browser-client"
REDIRECT_URI = "https://atlas.example.test/identity/callback"
KEY = b"oidc-login-session-test-key-32!!"


class FakeCodeExchanger:
    def __init__(self, response=None, error=None):
        self.response = response or OIDCTokenResponse("signed-id-token", "provider-access-token")
        self.error = error
        self.calls = []

    def exchange(self, code, code_verifier, redirect_uri):
        self.calls.append((code, code_verifier, redirect_uri))
        if self.error is not None:
            raise self.error
        return self.response


class FakeIDTokenVerifier:
    def __init__(self, claims=None, error=None):
        self.claims = claims
        self.error = error
        self.calls = []

    def verify(self, id_token, *, access_token=None):
        self.calls.append((id_token, access_token))
        if self.error is not None:
            raise self.error
        return self.claims


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

    linking_session = sessions.issue_session(account.account_id)
    linking_principal = AtlasSessionIdentityService(
        sessions, memberships
    ).authenticate(linking_session.token)

    transactions = SQLiteOIDCLoginTransactionStore(
        str(tmp_path / "login-transactions.sqlite"),
        KEY,
    )
    transactions.initialize()
    links = SQLiteOIDCAccountLinkRepository(accounts)
    links.initialize()
    account_links = OIDCAccountLinkService(links, transactions)

    link_start = transactions.begin()
    link_transaction = transactions.consume(link_start.state)
    link_claims = VerifiedIDTokenClaims(
        issuer=ISSUER,
        subject="provider-subject",
        audiences=(CLIENT_ID,),
        expires_at=time.time() + 300,
        issued_at=time.time(),
        nonce=link_start.nonce,
    )
    account_links.link_authenticated_account(
        linking_principal, link_claims, link_transaction
    )

    login_sessions = OIDCLoginSessionService(
        account_links, sessions, memberships
    )
    return {
        "account": account,
        "accounts": accounts,
        "sessions": sessions,
        "memberships": memberships,
        "transactions": transactions,
        "login_sessions": login_sessions,
        "database": database,
        "tmp_path": tmp_path,
    }


def _service(
    setup,
    start,
    *,
    subject="provider-subject",
    nonce=None,
    exchange_error=None,
    verifier_error=None,
    token_response=None,
):
    claims = VerifiedIDTokenClaims(
        issuer=ISSUER,
        subject=subject,
        audiences=(CLIENT_ID,),
        expires_at=time.time() + 300,
        issued_at=time.time(),
        nonce=start.nonce if nonce is None else nonce,
    )
    exchanger = FakeCodeExchanger(
        response=token_response,
        error=exchange_error,
    )
    verifier = FakeIDTokenVerifier(claims=claims, error=verifier_error)
    service = OIDCBrowserLoginService(
        transactions=setup["transactions"],
        exchanger=exchanger,
        id_token_verifier=verifier,
        login_sessions=setup["login_sessions"],
        redirect_uri=REDIRECT_URI,
    )
    return service, exchanger, verifier


def test_callback_exchanges_code_verifies_identity_and_issues_atlas_session(setup):
    start = setup["transactions"].begin()
    service, exchanger, verifier = _service(setup, start)

    issued = service.complete_callback("one-time-provider-code", start.state)

    assert exchanger.calls == [
        ("one-time-provider-code", start.code_verifier, REDIRECT_URI)
    ]
    assert verifier.calls == [("signed-id-token", "provider-access-token")]
    assert setup["sessions"].validate_session(issued.session.token).account_id == (
        setup["account"].account_id
    )
    assert setup["sessions"].validate_csrf_token(
        issued.session.token, issued.csrf_token
    ) is True
    assert issued.principal.tenant_id == "tenant-a"
    assert issued.session.token not in repr(issued)
    assert issued.csrf_token not in repr(issued)


def test_callback_state_can_be_consumed_only_once(setup):
    start = setup["transactions"].begin()
    service, exchanger, _ = _service(setup, start)

    service.complete_callback("one-time-provider-code", start.state)
    with pytest.raises(InvalidLoginTransaction):
        service.complete_callback("one-time-provider-code", start.state)

    assert len(exchanger.calls) == 1
    assert _session_count(setup["database"], active_only=True) == 2


def test_nonce_mismatch_does_not_issue_a_browser_session(setup):
    start = setup["transactions"].begin()
    service, _, _ = _service(setup, start, nonce="n" * 43)
    before = _session_count(setup["database"], active_only=True)

    with pytest.raises(InvalidLoginTransaction):
        service.complete_callback("one-time-provider-code", start.state)

    assert _session_count(setup["database"], active_only=True) == before


def test_unknown_external_subject_does_not_issue_a_browser_session(setup):
    start = setup["transactions"].begin()
    service, _, _ = _service(
        setup, start, subject="not-linked-to-an-atlas-account"
    )
    before = _session_count(setup["database"], active_only=True)

    with pytest.raises(OIDCAccountLinkNotFound):
        service.complete_callback("one-time-provider-code", start.state)

    assert _session_count(setup["database"], active_only=True) == before


def test_code_exchange_failure_is_sanitized_and_consumes_state(setup):
    start = setup["transactions"].begin()
    service, exchanger, _ = _service(
        setup,
        start,
        exchange_error=RuntimeError("private endpoint response and secret"),
    )

    with pytest.raises(OIDCBrowserLoginError) as error:
        service.complete_callback("one-time-provider-code", start.state)

    assert "private endpoint" not in str(error.value)
    assert "secret" not in str(error.value)
    assert len(exchanger.calls) == 1
    with pytest.raises(InvalidLoginTransaction):
        service.complete_callback("one-time-provider-code", start.state)


def test_invalid_id_token_is_sanitized_and_does_not_issue_a_session(setup):
    start = setup["transactions"].begin()
    service, _, _ = _service(
        setup, start, verifier_error=ValueError("private token contents")
    )
    before = _session_count(setup["database"], active_only=True)

    with pytest.raises(OIDCBrowserLoginError) as error:
        service.complete_callback("one-time-provider-code", start.state)

    assert "private token contents" not in str(error.value)
    assert _session_count(setup["database"], active_only=True) == before


def test_malformed_code_consumes_state_without_calling_provider(setup):
    start = setup["transactions"].begin()
    service, exchanger, _ = _service(setup, start)

    with pytest.raises(OIDCBrowserLoginError):
        service.complete_callback("code containing spaces", start.state)

    assert exchanger.calls == []
    with pytest.raises(InvalidLoginTransaction):
        service.complete_callback("one-time-provider-code", start.state)


def test_non_bearer_or_malformed_token_response_is_rejected(setup):
    start = setup["transactions"].begin()
    response = OIDCTokenResponse(
        "signed-id-token", "provider-access-token", token_type="MAC"
    )
    service, _, verifier = _service(
        setup, start, token_response=response
    )

    with pytest.raises(OIDCBrowserLoginError):
        service.complete_callback("one-time-provider-code", start.state)

    assert verifier.calls == []


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "http://atlas.example.test/identity/callback",
        "https://user:password@atlas.example.test/identity/callback",
        "https://atlas.example.test/identity/callback?next=https://evil.test",
        "https://atlas.example.test/identity/callback#fragment",
        " https://atlas.example.test/identity/callback",
    ],
)
def test_callback_requires_fixed_https_redirect_uri(setup, redirect_uri):
    start = setup["transactions"].begin()
    _, exchanger, verifier = _service(setup, start)

    with pytest.raises(ValueError):
        OIDCBrowserLoginService(
            transactions=setup["transactions"],
            exchanger=exchanger,
            id_token_verifier=verifier,
            login_sessions=setup["login_sessions"],
            redirect_uri=redirect_uri,
        )


def test_callback_and_account_link_services_must_share_transaction_store(setup):
    other = SQLiteOIDCLoginTransactionStore(
        str(setup["tmp_path"] / "other-transactions.sqlite"),
        KEY,
    )
    other.initialize()

    with pytest.raises(ValueError, match="share one transaction store"):
        OIDCBrowserLoginService(
            transactions=other,
            exchanger=FakeCodeExchanger(),
            id_token_verifier=FakeIDTokenVerifier(),
            login_sessions=setup["login_sessions"],
            redirect_uri=REDIRECT_URI,
        )
