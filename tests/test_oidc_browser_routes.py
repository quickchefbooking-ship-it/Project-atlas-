from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from atlas_engine.http_identity import require_verified_principal
from atlas_engine.oidc_browser_routes import (
    ATLAS_CSRF_COOKIE,
    ATLAS_OIDC_STATE_COOKIE,
    ATLAS_SESSION_COOKIE,
    OIDCBrowserLoginInitiator,
    router,
)
from atlas_engine.oidc_login_transaction import (
    InvalidLoginTransaction,
    SQLiteOIDCLoginTransactionStore,
)

KEY = b"atlas-oidc-route-key-32-bytes!!!"
AUTHORIZATION_ENDPOINT = "https://identity.example.test/authorize"
REDIRECT_URI = "https://atlas.example.test/identity/callback"


def _store(tmp_path):
    store = SQLiteOIDCLoginTransactionStore(
        str(tmp_path / "oidc-transactions.sqlite"),
        KEY,
    )
    store.initialize()
    return store


class FakeSessions:
    def __init__(self):
        self.revoked = []

    def revoke_session(self, token):
        self.revoked.append(token)
        return True


class FakeCallbackService:
    def __init__(self, transactions):
        self.transactions = transactions
        self.redirect_uri = REDIRECT_URI
        self.sessions = FakeSessions()
        self.memberships = object()
        self.login_sessions = SimpleNamespace(
            sessions=self.sessions,
            memberships=self.memberships,
        )
        self.calls = []
        self.fail = False

    def complete_callback(self, code, state):
        self.calls.append((code, state))
        self.transactions.consume(state)
        if self.fail:
            raise RuntimeError("private provider response and token details")
        session = SimpleNamespace(
            token="s" * 64,
            absolute_expires_at=(datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
        )
        return SimpleNamespace(
            session=session,
            csrf_token="c" * 64,
            principal=object(),
        )


def _app(initiator=None, callback=None):
    application = FastAPI()
    application.state.oidc_login_initiator = initiator
    application.state.oidc_browser_login_service = callback
    application.state.atlas_session_identity_service = None
    application.state.atlas_trusted_origins = frozenset()
    application.include_router(router)
    return application


def _start_login(client):
    response = client.get("/identity/login", follow_redirects=False)
    query = parse_qs(urlsplit(response.headers["location"]).query)
    return query["state"][0], response


def test_login_redirect_uses_server_generated_state_nonce_and_s256_without_verifier(tmp_path):
    transactions = _store(tmp_path)
    initiator = OIDCBrowserLoginInitiator(
        transactions,
        AUTHORIZATION_ENDPOINT,
        "atlas-browser-client",
        REDIRECT_URI,
    )
    callback = FakeCallbackService(transactions)
    client = TestClient(_app(initiator, callback), base_url="https://atlas.example.test")

    state, response = _start_login(client)

    assert response.status_code == 302
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["atlas-browser-client"]
    assert query["redirect_uri"] == [REDIRECT_URI]
    assert query["scope"] == ["openid"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"] == [state]
    assert len(query["state"][0]) >= 32
    assert len(query["nonce"][0]) >= 32
    assert len(query["code_challenge"][0]) == 43
    assert "code_verifier" not in query
    state_cookie = next(
        value for value in response.headers.get_list("set-cookie")
        if value.startswith(ATLAS_OIDC_STATE_COOKIE + "=")
    )
    assert "Secure" in state_cookie
    assert "HttpOnly" in state_cookie
    assert "Path=/" in state_cookie
    assert "SameSite=lax" in state_cookie


def test_callback_consumes_browser_bound_state_and_sets_session_and_csrf_cookies(tmp_path):
    transactions = _store(tmp_path)
    initiator = OIDCBrowserLoginInitiator(
        transactions,
        AUTHORIZATION_ENDPOINT,
        "atlas-browser-client",
        REDIRECT_URI,
    )
    callback = FakeCallbackService(transactions)
    application = _app(initiator, callback)
    client = TestClient(application, base_url="https://atlas.example.test")
    state, _ = _start_login(client)

    response = client.get(
        "/identity/callback",
        params={"code": "provider-one-time-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/professor/chat"
    assert response.headers["cache-control"] == "no-store"
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(value for value in cookies if value.startswith(ATLAS_SESSION_COOKIE + "="))
    csrf_cookie = next(value for value in cookies if value.startswith(ATLAS_CSRF_COOKIE + "="))
    state_cookie = next(value for value in cookies if value.startswith(ATLAS_OIDC_STATE_COOKIE + "="))
    assert "Secure" in session_cookie
    assert "HttpOnly" in session_cookie
    assert "Path=/" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "Secure" in csrf_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "Path=/" in csrf_cookie
    assert "SameSite=lax" in csrf_cookie
    assert "Max-Age=0" in state_cookie
    assert application.state.atlas_trusted_origins == frozenset({"https://atlas.example.test"})
    assert application.state.atlas_session_identity_service is not None
    assert callback.calls == [("provider-one-time-code", state)]


def test_callback_from_another_browser_does_not_consume_valid_state(tmp_path):
    transactions = _store(tmp_path)
    initiator = OIDCBrowserLoginInitiator(
        transactions,
        AUTHORIZATION_ENDPOINT,
        "atlas-browser-client",
        REDIRECT_URI,
    )
    callback = FakeCallbackService(transactions)
    client = TestClient(_app(initiator, callback), base_url="https://atlas.example.test")
    start = transactions.begin()

    client.cookies.set(
        ATLAS_OIDC_STATE_COOKIE,
        "x" * 43,
        domain="atlas.example.test",
        path="/",
    )
    response = client.get(
        "/identity/callback",
        params={"code": "provider-one-time-code", "state": start.state},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Sign-in could not be completed."
    assert callback.calls == []
    consumed = transactions.consume(start.state)
    assert consumed.expires_at > consumed.created_at


def test_provider_error_consumes_browser_bound_state_and_returns_generic_error(tmp_path):
    transactions = _store(tmp_path)
    initiator = OIDCBrowserLoginInitiator(
        transactions,
        AUTHORIZATION_ENDPOINT,
        "atlas-browser-client",
        REDIRECT_URI,
    )
    callback = FakeCallbackService(transactions)
    client = TestClient(_app(initiator, callback), base_url="https://atlas.example.test")
    state, _ = _start_login(client)

    response = client.get(
        "/identity/callback",
        params={"error": "access_denied", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Sign-in was not completed."
    assert response.headers["cache-control"] == "no-store"
    with pytest.raises(InvalidLoginTransaction):
        transactions.consume(state)
    assert callback.calls == []


def test_callback_failure_is_sanitized_and_does_not_set_session_cookies(tmp_path):
    transactions = _store(tmp_path)
    initiator = OIDCBrowserLoginInitiator(
        transactions,
        AUTHORIZATION_ENDPOINT,
        "atlas-browser-client",
        REDIRECT_URI,
    )
    callback = FakeCallbackService(transactions)
    callback.fail = True
    client = TestClient(_app(initiator, callback), base_url="https://atlas.example.test")
    state, _ = _start_login(client)

    response = client.get(
        "/identity/callback",
        params={"code": "provider-one-time-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Sign-in could not be completed."
    assert "private provider response" not in response.text
    cookies = response.headers.get_list("set-cookie")
    assert not any(value.startswith(ATLAS_SESSION_COOKIE + "=") for value in cookies)
    assert not any(value.startswith(ATLAS_CSRF_COOKIE + "=") for value in cookies)
    assert any(value.startswith(ATLAS_OIDC_STATE_COOKIE + "=") and "Max-Age=0" in value for value in cookies)


def test_routes_fail_closed_until_server_services_are_injected():
    client = TestClient(_app(), base_url="https://atlas.example.test")

    login = client.get("/identity/login", follow_redirects=False)
    callback = client.get(
        "/identity/callback",
        params={"code": "provider-code", "state": "s" * 43},
        follow_redirects=False,
    )

    assert login.status_code == 503
    assert callback.status_code == 503
    assert "provider" not in login.text.lower()


def test_logout_revokes_session_and_clears_both_host_only_cookies():
    application = _app()
    sessions = FakeSessions()
    application.state.atlas_session_identity_service = SimpleNamespace(sessions=sessions)
    application.dependency_overrides[require_verified_principal] = lambda: object()
    client = TestClient(application, base_url="https://atlas.example.test")

    client.cookies.set(
        ATLAS_SESSION_COOKIE,
        "s" * 64,
        domain="atlas.example.test",
        path="/",
    )
    client.cookies.set(
        ATLAS_CSRF_COOKIE,
        "c" * 64,
        domain="atlas.example.test",
        path="/",
    )
    response = client.post(
        "/identity/logout",
        headers={
            "Origin": "https://atlas.example.test",
            "Sec-Fetch-Site": "same-origin",
            "X-Atlas-CSRF": "c" * 64,
        },
    )

    assert response.status_code == 204
    assert sessions.revoked == ["s" * 64]
    cookies = response.headers.get_list("set-cookie")
    assert any(value.startswith(ATLAS_SESSION_COOKIE + "=") and "Max-Age=0" in value for value in cookies)
    assert any(value.startswith(ATLAS_CSRF_COOKIE + "=") and "Max-Age=0" in value for value in cookies)
    assert any(value.startswith(ATLAS_OIDC_STATE_COOKIE + "=") and "Max-Age=0" in value for value in cookies)


@pytest.mark.parametrize(
    "authorization_endpoint,redirect_uri",
    [
        ("http://identity.example.test/authorize", REDIRECT_URI),
        ("https://user:pass@identity.example.test/authorize", REDIRECT_URI),
        ("https://identity.example.test/authorize#fragment", REDIRECT_URI),
        ("https://identity.example.test/authorize#", REDIRECT_URI),
        ("https://identity.example.test/authorize?state=attacker", REDIRECT_URI),
        (AUTHORIZATION_ENDPOINT, "http://atlas.example.test/identity/callback"),
        (AUTHORIZATION_ENDPOINT, "https://atlas.example.test/auth/callback"),
        (AUTHORIZATION_ENDPOINT, "https://atlas.example.test/identity/callback?"),
        (AUTHORIZATION_ENDPOINT, "https://atlas.example.test/identity/callback?next=https://evil.test"),
    ],
)
def test_initiator_rejects_untrusted_or_ambiguous_endpoints(
    tmp_path, authorization_endpoint, redirect_uri
):
    with pytest.raises(ValueError):
        OIDCBrowserLoginInitiator(
            _store(tmp_path),
            authorization_endpoint,
            "atlas-browser-client",
            redirect_uri,
        )
