"""End-to-end tests for the hosted OIDC browser route composition.

These tests use real Atlas account, membership, PKCE transaction, account-link,
session, CSRF and HTTP route services. Only the external code exchanger and
cryptographic ID-token verifier are controlled test doubles; no live provider
or deployment secret is required.
"""
import sqlite3
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from atlas_engine.account_identity import (
    Argon2idCredentialHasher,
    SQLiteAccountRepository,
)
from atlas_engine.atlas_session_identity import (
    ATLAS_IDENTITY_ISSUER,
    AtlasSessionIdentityService,
)
from atlas_engine.http_identity import (
    ATLAS_CSRF_HEADER,
    ATLAS_SESSION_COOKIE,
    require_verified_principal,
)
from atlas_engine.oidc_account_link import (
    IDENTITY_LINK_SCOPE,
    OIDCAccountLinkService,
    SQLiteOIDCAccountLinkRepository,
)
from atlas_engine.oidc_browser_login import (
    OIDCBrowserLoginService,
    OIDCTokenResponse,
)
from atlas_engine.oidc_browser_routes import (
    ATLAS_CSRF_COOKIE,
    ATLAS_OIDC_STATE_COOKIE,
    OIDCBrowserLoginInitiator,
    router,
)
from atlas_engine.oidc_id_token_verifier import VerifiedIDTokenClaims
from atlas_engine.oidc_login_session import OIDCLoginSessionService
from atlas_engine.oidc_login_transaction import (
    InvalidLoginTransaction,
    SQLiteOIDCLoginTransactionStore,
)
from atlas_engine.session_identity import (
    InvalidSession,
    SQLiteSessionRepository,
)
from atlas_engine.tenant_membership import SQLiteMembershipRegistry


ISSUER = "https://idp.example.test/"
CLIENT_ID = "atlas-browser-client"
SUBJECT = "provider-subject"
AUTHORIZATION_ENDPOINT = "https://identity.example.test/authorize"
REDIRECT_URI = "https://atlas.example.test/identity/callback"
TRANSACTION_KEY = b"oidc-login-session-test-key-32!!"
BASE_URL = "https://atlas.example.test"


class FakeCodeExchanger:
    """Deterministic token endpoint boundary; no network calls are made."""

    def __init__(self):
        self.calls = []

    def exchange(self, code, code_verifier, redirect_uri):
        self.calls.append((code, code_verifier, redirect_uri))
        return OIDCTokenResponse(
            "signed-id-token",
            "provider-access-token",
        )


class NonceBoundTestVerifier:
    """Return claims bound to the exact transaction created by the login route."""

    def __init__(self, starts, *, subject=SUBJECT):
        self.starts = starts
        self.subject = subject
        self.calls = []

    def verify(self, id_token, *, access_token=None):
        self.calls.append((id_token, access_token))
        if id_token != "signed-id-token" or access_token != "provider-access-token":
            raise ValueError("Unexpected test token material.")
        if not self.starts:
            raise AssertionError("The login route did not create a PKCE transaction.")
        return VerifiedIDTokenClaims(
            issuer=ISSUER,
            subject=self.subject,
            audiences=(CLIENT_ID,),
            expires_at=time.time() + 300,
            issued_at=time.time(),
            nonce=self.starts[-1].nonce,
        )


def _active_session_count(database):
    connection = sqlite3.connect(database)
    try:
        return connection.execute(
            """SELECT count(*) FROM atlas_sessions
               WHERE revoked_at IS NULL AND rotated_to_session_id IS NULL"""
        ).fetchone()[0]
    finally:
        connection.close()


def _build_browser_flow(tmp_path, monkeypatch, *, login_subject=SUBJECT):
    """Compose real Atlas services behind the hosted browser router."""
    account_database = str(tmp_path / "atlas-identity.sqlite")
    accounts = SQLiteAccountRepository(
        account_database,
        Argon2idCredentialHasher(
            time_cost=1,
            memory_cost=19456,
            parallelism=1,
        ),
    )
    accounts.initialize()
    account = accounts.create_pending_account(
        "alice@example.test",
        "a sufficiently long account password",
    )
    accounts.set_account_status(account.account_id, "active")

    sessions = SQLiteSessionRepository(account_database)
    sessions.initialize()

    memberships = SQLiteMembershipRegistry(
        str(tmp_path / "memberships.sqlite")
    )
    memberships.initialize()
    memberships.create_tenant("tenant-a", "Tenant A")
    memberships.provision_membership(
        ATLAS_IDENTITY_ISSUER,
        account.account_id,
        "tenant-a",
        {IDENTITY_LINK_SCOPE, "professor:chat"},
    )

    transactions = SQLiteOIDCLoginTransactionStore(
        str(tmp_path / "login-transactions.sqlite"),
        TRANSACTION_KEY,
    )
    transactions.initialize()

    account_link_repository = SQLiteOIDCAccountLinkRepository(accounts)
    account_link_repository.initialize()
    account_links = OIDCAccountLinkService(
        account_link_repository,
        transactions,
    )

    # Provision the external identity explicitly through an authenticated Atlas
    # account, using a consumed test transaction and its matching nonce.
    linking_session = sessions.issue_session(account.account_id)
    linking_principal = AtlasSessionIdentityService(
        sessions,
        memberships,
    ).authenticate(linking_session.token)
    linking_start = transactions.begin()
    linking_transaction = transactions.consume(linking_start.state)
    linking_claims = VerifiedIDTokenClaims(
        issuer=ISSUER,
        subject=SUBJECT,
        audiences=(CLIENT_ID,),
        expires_at=time.time() + 300,
        issued_at=time.time(),
        nonce=linking_start.nonce,
    )
    account_links.link_authenticated_account(
        linking_principal,
        linking_claims,
        linking_transaction,
    )

    login_sessions = OIDCLoginSessionService(
        account_links,
        sessions,
        memberships,
    )

    # Capture the transaction created by GET /identity/login so the controlled
    # verifier can return a nonce bound to that exact state.
    starts = []
    original_begin = transactions.begin

    def tracked_begin():
        started = original_begin()
        starts.append(started)
        return started

    monkeypatch.setattr(transactions, "begin", tracked_begin)

    exchanger = FakeCodeExchanger()
    verifier = NonceBoundTestVerifier(starts, subject=login_subject)
    callback_service = OIDCBrowserLoginService(
        transactions=transactions,
        exchanger=exchanger,
        id_token_verifier=verifier,
        login_sessions=login_sessions,
        redirect_uri=REDIRECT_URI,
    )
    initiator = OIDCBrowserLoginInitiator(
        transactions=transactions,
        authorization_endpoint=AUTHORIZATION_ENDPOINT,
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT_URI,
    )

    application = FastAPI()
    application.state.oidc_login_initiator = initiator
    application.state.oidc_browser_login_service = callback_service
    application.state.atlas_session_identity_service = None
    application.state.atlas_trusted_origins = frozenset()
    application.include_router(router)

    @application.get("/identity/me")
    def identity_me(principal=Depends(require_verified_principal)):
        return {
            "issuer": principal.issuer,
            "subject": principal.subject,
            "tenant_id": principal.tenant_id,
            "scopes": sorted(principal.scopes),
        }

    @application.post("/integration/protected")
    def protected_write(principal=Depends(require_verified_principal)):
        return {"tenant_id": principal.tenant_id}

    client = TestClient(application, base_url=BASE_URL)
    return {
        "client": client,
        "account": account,
        "database": account_database,
        "sessions": sessions,
        "transactions": transactions,
        "starts": starts,
        "exchanger": exchanger,
        "verifier": verifier,
        "application": application,
        "login_sessions": login_sessions,
    }


def _start_login(client):
    response = client.get("/identity/login", follow_redirects=False)
    assert response.status_code == 302
    parameters = parse_qs(urlsplit(response.headers["location"]).query)
    return parameters["state"][0], parameters


def _callback(client, state):
    return client.get(
        "/identity/callback",
        params={"code": "one-time-provider-code", "state": state},
        follow_redirects=False,
    )


def _same_origin_headers(csrf_token=None):
    headers = {
        "Origin": "https://atlas.example.test",
        "Sec-Fetch-Site": "same-origin",
    }
    if csrf_token is not None:
        headers[ATLAS_CSRF_HEADER] = csrf_token
    return headers


def test_hosted_browser_flow_issues_a_tenant_session_and_supports_csrf_and_logout(
    tmp_path, monkeypatch
):
    flow = _build_browser_flow(tmp_path, monkeypatch)
    client = flow["client"]

    state, parameters = _start_login(client)
    assert parameters["response_type"] == ["code"]
    assert parameters["client_id"] == [CLIENT_ID]
    assert parameters["redirect_uri"] == [REDIRECT_URI]
    assert parameters["code_challenge_method"] == ["S256"]
    assert "code_verifier" not in parameters
    assert client.cookies.get(ATLAS_OIDC_STATE_COOKIE) == state

    callback = _callback(client, state)

    assert callback.status_code == 303
    assert callback.headers["location"] == "/professor/chat"
    assert callback.headers["cache-control"] == "no-store"
    assert flow["exchanger"].calls == [
        (
            "one-time-provider-code",
            flow["starts"][0].code_verifier,
            REDIRECT_URI,
        )
    ]
    assert flow["verifier"].calls == [
        ("signed-id-token", "provider-access-token")
    ]

    identity = client.get("/identity/me")
    assert identity.status_code == 200
    assert identity.json() == {
        "issuer": ATLAS_IDENTITY_ISSUER,
        "subject": flow["account"].account_id,
        "tenant_id": "tenant-a",
        "scopes": [IDENTITY_LINK_SCOPE, "professor:chat"],
    }

    session_token = client.cookies.get(ATLAS_SESSION_COOKIE)
    csrf_token = client.cookies.get(ATLAS_CSRF_COOKIE)
    assert session_token
    assert csrf_token

    rejected_write = client.post(
        "/integration/protected",
        headers=_same_origin_headers(),
    )
    assert rejected_write.status_code == 403

    accepted_write = client.post(
        "/integration/protected",
        headers=_same_origin_headers(csrf_token),
    )
    assert accepted_write.status_code == 200
    assert accepted_write.json() == {"tenant_id": "tenant-a"}

    logout = client.post(
        "/identity/logout",
        headers=_same_origin_headers(csrf_token),
    )
    assert logout.status_code == 204
    with pytest.raises(InvalidSession):
        flow["sessions"].validate_session(session_token)


def test_unlinked_external_subject_fails_closed_without_issuing_a_session(
    tmp_path, monkeypatch
):
    flow = _build_browser_flow(
        tmp_path,
        monkeypatch,
        login_subject="not-explicitly-linked",
    )
    before = _active_session_count(flow["database"])

    state, _parameters = _start_login(flow["client"])
    callback = _callback(flow["client"], state)

    assert callback.status_code == 400
    assert callback.json() == {"detail": "Sign-in could not be completed."}
    assert not flow["client"].cookies.get(ATLAS_SESSION_COOKIE)
    assert not flow["client"].cookies.get(ATLAS_CSRF_COOKIE)
    assert _active_session_count(flow["database"]) == before
    assert len(flow["exchanger"].calls) == 1


def test_replayed_hosted_callback_cannot_issue_a_second_atlas_session(
    tmp_path, monkeypatch
):
    flow = _build_browser_flow(tmp_path, monkeypatch)
    client = flow["client"]

    state, _parameters = _start_login(client)
    first = _callback(client, state)
    assert first.status_code == 303

    session_token = client.cookies.get(ATLAS_SESSION_COOKIE)
    before = _active_session_count(flow["database"])
    assert session_token

    # Simulate a browser retry after the first callback cleared the state cookie.
    client.cookies.set(
        ATLAS_OIDC_STATE_COOKIE,
        state,
        domain="atlas.example.test",
        path="/",
    )
    replay = _callback(client, state)

    assert replay.status_code == 400
    assert replay.json() == {"detail": "Sign-in could not be completed."}
    assert len(flow["exchanger"].calls) == 1
    assert _active_session_count(flow["database"]) == before
    assert flow["sessions"].validate_session(session_token).account_id == (
        flow["account"].account_id
    )


def test_hosted_browser_flow_uses_real_token_exchange_and_id_token_verification(
    tmp_path, monkeypatch
):
    """Exercise the real adapters together without contacting a live provider."""
    import httpx
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from types import SimpleNamespace

    from atlas_engine.oidc_contract import OIDCProviderConfig
    from atlas_engine.oidc_http_token_exchange import HTTPSOIDCAuthorizationCodeExchanger
    from atlas_engine.oidc_id_token_verifier import PyJWTIDTokenVerifier

    flow = _build_browser_flow(tmp_path, monkeypatch)
    state, _parameters = _start_login(flow["client"])

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    signed_id_token = jwt.encode(
        {
            "iss": ISSUER,
            "sub": SUBJECT,
            "aud": CLIENT_ID,
            "exp": now + 300,
            "iat": now,
            "nonce": flow["starts"][0].nonce,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "atlas-test-key"},
    )

    requests = []

    def token_endpoint(request):
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "id_token": signed_id_token,
                "access_token": "provider-access-token",
                "token_type": "Bearer",
            },
        )

    exchanger = HTTPSOIDCAuthorizationCodeExchanger(
        token_endpoint="https://identity.example.test/oauth/token",
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT_URI,
        transport=httpx.MockTransport(token_endpoint),
    )

    class LocalPinnedJWKS:
        def get_signing_key_from_jwt(self, token):
            assert token == signed_id_token
            return SimpleNamespace(key=private_key.public_key())

    verifier = PyJWTIDTokenVerifier(
        OIDCProviderConfig(
            issuer=ISSUER,
            audience="atlas-api",
            jwks_uri=ISSUER + ".well-known/jwks.json",
            allowed_algorithms=frozenset({"RS256"}),
            clock_skew_seconds=0,
        ),
        CLIENT_ID,
        LocalPinnedJWKS(),
    )
    flow["application"].state.oidc_browser_login_service = OIDCBrowserLoginService(
        transactions=flow["transactions"],
        exchanger=exchanger,
        id_token_verifier=verifier,
        login_sessions=flow["login_sessions"],
        redirect_uri=REDIRECT_URI,
    )

    callback = _callback(flow["client"], state)

    assert callback.status_code == 303
    assert callback.headers["location"] == "/professor/chat"
    assert len(requests) == 1
    form = parse_qs(requests[0].content.decode())
    assert form == {
        "grant_type": ["authorization_code"],
        "code": ["one-time-provider-code"],
        "redirect_uri": [REDIRECT_URI],
        "code_verifier": [flow["starts"][0].code_verifier],
        "client_id": [CLIENT_ID],
    }

    identity = flow["client"].get("/identity/me")
    assert identity.status_code == 200
    assert identity.json()["tenant_id"] == "tenant-a"
    assert identity.json()["subject"] == flow["account"].account_id
