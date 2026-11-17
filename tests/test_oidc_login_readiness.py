import app as application
from types import SimpleNamespace


def _configure_complete_login(monkeypatch):
    values = {
        "ATLAS_OIDC_ISSUER": "https://identity.example.test",
        "ATLAS_OIDC_AUDIENCE": "atlas-api",
        "ATLAS_OIDC_JWKS_URI": "https://identity.example.test/.well-known/jwks.json",
        "ATLAS_OIDC_ALLOWED_ALGORITHMS": "RS256",
        "ATLAS_MEMBERSHIP_DB_PATH": "/var/lib/atlas/membership.sqlite",
        "ATLAS_OIDC_AUTHORIZATION_ENDPOINT": "https://identity.example.test/authorize",
        "ATLAS_OIDC_TOKEN_ENDPOINT": "https://identity.example.test/token",
        "ATLAS_OIDC_CLIENT_ID": "atlas-browser",
        "ATLAS_OIDC_REDIRECT_URI": "https://atlas.example.test/identity/callback",
        "ATLAS_ACCOUNT_DB_PATH": "/var/lib/atlas/accounts.sqlite",
        "ATLAS_OIDC_LOGIN_TRANSACTION_DB_PATH": "/var/lib/atlas/oidc-login-transactions.sqlite",
        "ATLAS_OIDC_LOGIN_TRANSACTION_KEY_HEX": "11" * 32,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_login_readiness_reports_missing_settings_without_exposing_secrets(monkeypatch):
    for name in application.OIDC_BROWSER_LOGIN_REQUIRED_SETTINGS:
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
    assert set(result["hosted_login"]["missing_settings"]) == set(
        application.OIDC_BROWSER_LOGIN_REQUIRED_SETTINGS
    )
    assert result["hosted_login"]["missing_routes"] == []
    assert set(result["hosted_login"]["missing_services"]) == {
        "authorization_redirect_service",
        "callback_session_service",
    }
    assert "client_secret" not in str(result).lower()


def test_login_readiness_does_not_mark_configuration_as_implemented(monkeypatch):
    _configure_complete_login(monkeypatch)

    result = application.identity_login_readiness()

    assert result["status"] == "routes_registered_unconfigured"
    assert result["api_verifier"]["configured"] is True
    assert result["api_verifier"]["missing_settings"] == []
    assert result["hosted_login"]["configured"] is True
    assert result["hosted_login"]["configuration_valid"] is True
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
    transaction_store = object()
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
                    transactions=transaction_store,
                    redirect_uri="https://atlas.example.test/identity/callback",
                    begin_login=lambda: "https://identity.example.test/authorize",
                ),
                oidc_browser_login_service=SimpleNamespace(
                    transactions=transaction_store,
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
    assert result["hosted_login"]["configuration_valid"] is True
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



def test_login_readiness_reports_invalid_complete_startup_configuration(monkeypatch):
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
                oidc_login_initiator=None,
                oidc_browser_login_service=None,
                oidc_browser_login_configuration_error=True,
            ),
        ),
    )

    result = application.identity_login_readiness()

    assert result["status"] == "configuration_invalid"
    assert result["hosted_login"]["configured"] is True
    assert result["hosted_login"]["configuration_valid"] is False
    assert result["hosted_login"]["services_configured"] is False


def test_launch_readiness_does_not_treat_environment_strings_as_composed_login(monkeypatch):
    _configure_complete_login(monkeypatch)
    monkeypatch.setattr(
        application,
        "app",
        SimpleNamespace(
            state=SimpleNamespace(
                identity_service=object(),
                tenant_data_path="/var/lib/atlas/tenant.sqlite",
                conversation_service=SimpleNamespace(is_configured=True),
                oidc_login_initiator=None,
                oidc_browser_login_service=None,
                oidc_browser_login_configuration_error=False,
            )
        ),
    )

    result = application.launch_readiness()

    assert result["checks"]["hosted_browser_login_configuration"] is False
    assert "hosted_browser_login_configuration" in result["blockers"]
    assert result["checks"]["live_provider_round_trip_verified"] is False
    assert result["execution_enabled"] is False
