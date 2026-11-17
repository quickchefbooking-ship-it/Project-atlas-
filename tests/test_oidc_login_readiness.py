import app as application
from types import SimpleNamespace


def _configure_complete_login(monkeypatch):
    values = {
        "ATLAS_OIDC_ISSUER": "https://identity.example.test",
        "ATLAS_OIDC_AUDIENCE": "atlas-api",
        "ATLAS_OIDC_JWKS_URI": "https://identity.example.test/.well-known/jwks.json",
        "ATLAS_OIDC_ALLOWED_ALGORITHMS": "RS256",
        "ATLAS_MEMBERSHIP_DB_PATH": "/var/lib/atlas/membership.sqlite",
        "ATLAS_OIDC_CLIENT_ID": "atlas-browser",
        "ATLAS_OIDC_REDIRECT_URI": "https://atlas.example.test/auth/callback",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_login_readiness_reports_missing_settings_without_exposing_secrets(monkeypatch):
    for name in (
        "ATLAS_OIDC_ISSUER",
        "ATLAS_OIDC_AUDIENCE",
        "ATLAS_OIDC_JWKS_URI",
        "ATLAS_OIDC_ALLOWED_ALGORITHMS",
        "ATLAS_MEMBERSHIP_DB_PATH",
        "ATLAS_OIDC_CLIENT_ID",
        "ATLAS_OIDC_REDIRECT_URI",
    ):
        monkeypatch.delenv(name, raising=False)

    result = application.identity_login_readiness()

    assert result["status"] == "not_configured"
    assert result["api_verifier"]["configured"] is False
    assert set(result["api_verifier"]["missing_settings"]) == {
        "ATLAS_OIDC_ISSUER",
        "ATLAS_OIDC_AUDIENCE",
        "ATLAS_OIDC_JWKS_URI",
        "ATLAS_OIDC_ALLOWED_ALGORITHMS",
        "ATLAS_MEMBERSHIP_DB_PATH",
    }
    assert result["hosted_login"]["configured"] is False
    assert result["hosted_login"]["implemented"] is False
    assert set(result["hosted_login"]["missing_settings"]) == {
        "ATLAS_OIDC_CLIENT_ID",
        "ATLAS_OIDC_REDIRECT_URI",
    }
    assert result["hosted_login"]["missing_routes"] == []
    assert set(result["hosted_login"]["missing_services"]) == {
        "authorization_redirect_service",
        "callback_session_service",
    }
    assert "client_secret" not in str(result).lower()
    assert "token" not in str(result).lower()


def test_login_readiness_does_not_mark_configuration_as_implemented(monkeypatch):
    _configure_complete_login(monkeypatch)

    result = application.identity_login_readiness()

    assert result["status"] == "routes_registered_unconfigured"
    assert result["api_verifier"]["configured"] is True
    assert result["api_verifier"]["missing_settings"] == []
    assert result["hosted_login"]["configured"] is True
    assert result["hosted_login"]["implemented"] is False
    assert result["hosted_login"]["routes_registered"] is True
    assert result["hosted_login"]["services_configured"] is False
    assert result["hosted_login"]["missing_settings"] == []
    assert result["hosted_login"]["missing_routes"] == []
    assert set(result["hosted_login"]["missing_services"]) == {
        "authorization_redirect_service",
        "callback_session_service",
    }
    assert result["hosted_login"]["flow"] == "authorization_code_pkce"
    assert "https://identity.example.test" not in str(result)
    assert "atlas-browser" not in str(result)


def test_login_readiness_distinguishes_registered_routes_from_verified_login(monkeypatch):
    _configure_complete_login(monkeypatch)
    monkeypatch.setattr(
        application,
        "app",
        SimpleNamespace(
            routes=[
                SimpleNamespace(path="/identity/login", methods={"GET"}),
                SimpleNamespace(path="/identity/callback", methods={"GET"}),
                SimpleNamespace(path="/identity/logout", methods={"POST"}),
            ],
            state=SimpleNamespace(
                oidc_login_initiator=SimpleNamespace(
                    transactions=(transactions := object()),
                    redirect_uri="https://atlas.example.test/identity/callback",
                    begin_login=lambda: "https://identity.example.test/authorize",
                ),
                oidc_browser_login_service=SimpleNamespace(
                    transactions=transactions,
                    redirect_uri="https://atlas.example.test/identity/callback",
                    login_sessions=object(),
                    complete_callback=lambda code, state: object(),
                ),
            ),
        ),
    )

    result = application.identity_login_readiness()

    assert result["status"] == "routes_registered_unverified"
    assert result["hosted_login"]["configured"] is True
    assert result["hosted_login"]["implemented"] is True
    assert result["hosted_login"]["routes_registered"] is True
    assert result["hosted_login"]["services_configured"] is True
    assert result["hosted_login"]["missing_routes"] == []
    assert result["hosted_login"]["missing_services"] == []
    assert "does not prove a successful sign-in or callback round trip" in result["note"]

def test_login_readiness_rejects_mismatched_callback_transaction_store(monkeypatch):
    _configure_complete_login(monkeypatch)
    monkeypatch.setattr(
        application,
        "app",
        SimpleNamespace(
            routes=[
                SimpleNamespace(path="/identity/login", methods={"GET"}),
                SimpleNamespace(path="/identity/callback", methods={"GET"}),
                SimpleNamespace(path="/identity/logout", methods={"POST"}),
            ],
            state=SimpleNamespace(
                oidc_login_initiator=SimpleNamespace(
                    transactions=object(),
                    redirect_uri="https://atlas.example.test/identity/callback",
                    begin_login=lambda: "https://identity.example.test/authorize",
                ),
                oidc_browser_login_service=SimpleNamespace(
                    transactions=object(),
                    redirect_uri="https://atlas.example.test/identity/callback",
                    login_sessions=object(),
                    complete_callback=lambda code, state: object(),
                ),
            ),
        ),
    )

    result = application.identity_login_readiness()

    assert result["status"] == "routes_registered_unconfigured"
    assert result["hosted_login"]["services_configured"] is False
    assert set(result["hosted_login"]["missing_services"]) == {
        "authorization_redirect_service",
        "callback_session_service",
    }
