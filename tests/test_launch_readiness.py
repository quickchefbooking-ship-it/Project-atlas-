from types import SimpleNamespace

import app as application


def test_launch_readiness_reports_unconfigured_services_and_live_round_trip(monkeypatch):
    monkeypatch.delenv("ATLAS_OIDC_CLIENT_ID", raising=False)
    monkeypatch.delenv("ATLAS_OIDC_REDIRECT_URI", raising=False)
    application.app.state.identity_service = None
    application.app.state.tenant_data_path = None
    application.app.state.conversation_service = SimpleNamespace(is_configured=False)

    result = application.launch_readiness()

    assert result["status"] == "not_ready"
    assert result["checks"] == {
        "verified_api_identity": False,
        "hosted_browser_login_configuration": False,
        "tenant_data_storage": False,
        "reasoning_provider_configured": False,
        "live_provider_round_trip_verified": False,
    }
    assert set(result["blockers"]) == set(result["checks"])
    assert result["execution_enabled"] is False
    assert "does not prove a successful" in result["note"] or "real provider conversation" in result["note"]


def test_launch_readiness_never_confuses_configuration_with_live_provider_proof(monkeypatch):
    monkeypatch.setenv("ATLAS_OIDC_CLIENT_ID", "test-client")
    monkeypatch.setenv("ATLAS_OIDC_REDIRECT_URI", "https://example.test/callback")
    application.app.state.identity_service = object()
    application.app.state.tenant_data_path = "/tmp/test-tenant-db"
    application.app.state.conversation_service = SimpleNamespace(is_configured=True)

    result = application.launch_readiness()

    assert result["checks"]["verified_api_identity"] is True
    assert result["checks"]["hosted_browser_login_configuration"] is True
    assert result["checks"]["tenant_data_storage"] is True
    assert result["checks"]["reasoning_provider_configured"] is True
    assert result["checks"]["live_provider_round_trip_verified"] is False
    assert result["status"] == "not_ready"
    assert result["blockers"] == ["live_provider_round_trip_verified"]
