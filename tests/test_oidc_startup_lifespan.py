import asyncio
from types import SimpleNamespace

from fastapi import FastAPI

import app as application


def test_lifespan_injects_matching_hosted_login_services_without_enabling_execution(monkeypatch):
    transactions = object()
    initiator = SimpleNamespace(
        transactions=transactions,
        redirect_uri="https://atlas.example.test/identity/callback",
        begin_login=lambda: "https://identity.example.test/authorize",
    )
    callback = SimpleNamespace(
        transactions=transactions,
        redirect_uri=initiator.redirect_uri,
        login_sessions=object(),
        complete_callback=lambda code, state: object(),
    )
    calls = {}

    monkeypatch.setattr(application, "load_bundled_knowledge", lambda: 0)
    monkeypatch.setattr(application.storage, "get_source", lambda *_args: object())
    monkeypatch.setattr(application, "_identity_service_from_environment", lambda: object())
    monkeypatch.setattr(
        application,
        "_initialize_tenant_data_store",
        lambda: "/tmp/atlas-tenant-test.sqlite",
    )

    def compose(**kwargs):
        calls.update(kwargs)
        return initiator, callback

    monkeypatch.setattr(application, "build_oidc_browser_login_services", compose)
    monkeypatch.setattr(application, "load_provider_from_environment", lambda: None)

    test_app = FastAPI()

    async def run_lifespan():
        async with application.lifespan(test_app):
            assert test_app.state.oidc_login_initiator is initiator
            assert test_app.state.oidc_browser_login_service is callback
            assert test_app.state.oidc_browser_login_configuration_error is False
            assert test_app.state.atlas_session_identity_service is None
            assert test_app.state.atlas_trusted_origins == frozenset()
            assert test_app.state.capability_execution_enabled is False

    monkeypatch.setenv("ATLAS_CAPABILITY_EXECUTION_ENABLED", "false")
    asyncio.run(run_lifespan())

    assert calls["tenant_database_path"] == "/tmp/atlas-tenant-test.sqlite"
    assert calls["membership_registry"] is None
