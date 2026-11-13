from fastapi.testclient import TestClient

import app as app_module


def test_private_routes_fail_closed_when_api_key_is_not_configured(monkeypatch):
    monkeypatch.setattr(app_module, "API_REQUIRE_AUTH", True)
    monkeypatch.setattr(app_module, "API_KEY", None)
    monkeypatch.delenv("ATLAS_API_KEY", raising=False)

    response = TestClient(app_module.app).get("/tasks")

    assert response.status_code == 503
    assert TestClient(app_module.app).get("/health").status_code == 200


def test_private_routes_require_the_configured_api_key(monkeypatch):
    monkeypatch.setattr(app_module, "API_REQUIRE_AUTH", True)
    monkeypatch.setattr(app_module, "API_KEY", "test-secret")
    monkeypatch.delenv("ATLAS_API_KEY", raising=False)
    client = TestClient(app_module.app)

    assert client.get("/tasks").status_code == 401
    response = client.get("/tasks", headers={"X-API-Key": "test-secret"})

    assert response.status_code == 200
