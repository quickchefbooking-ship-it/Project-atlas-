import app as application


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
    assert set(result["hosted_login"]["missing_settings"]) == {
        "ATLAS_OIDC_CLIENT_ID",
        "ATLAS_OIDC_REDIRECT_URI",
    }
    assert "client_secret" not in str(result).lower()
    assert "token" not in str(result).lower()


def test_login_readiness_requires_complete_verifier_and_hosted_client(monkeypatch):
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

    result = application.identity_login_readiness()

    assert result["status"] == "ready"
    assert result["api_verifier"]["configured"] is True
    assert result["api_verifier"]["missing_settings"] == []
    assert result["hosted_login"]["configured"] is True
    assert result["hosted_login"]["missing_settings"] == []
    assert result["hosted_login"]["flow"] == "authorization_code_pkce"
    assert "https://identity.example.test" not in str(result)
    assert "atlas-browser" not in str(result)
