from fastapi.testclient import TestClient

import app as app_module


def test_build_info_returns_a_normalized_full_git_revision(monkeypatch):
    monkeypatch.setenv("ATLAS_BUILD_REVISION", "A" * 40)

    response = TestClient(app_module.app).get("/build-info")

    assert response.status_code == 200
    assert response.json() == {"revision": "a" * 40, "status": "known"}


def test_build_info_reports_unknown_when_revision_is_missing(monkeypatch):
    monkeypatch.delenv("ATLAS_BUILD_REVISION", raising=False)

    response = TestClient(app_module.app).get("/build-info")

    assert response.status_code == 200
    assert response.json() == {"revision": None, "status": "unknown"}


def test_build_info_does_not_echo_malformed_revision_values(monkeypatch):
    invalid_value = "not-a-git-sha-or-secret"
    monkeypatch.setenv("ATLAS_BUILD_REVISION", invalid_value)

    response = TestClient(app_module.app).get("/build-info")

    assert response.status_code == 200
    assert response.json() == {"revision": None, "status": "unknown"}
    assert invalid_value not in response.text


def test_build_info_remains_public_when_api_key_authentication_is_enabled(monkeypatch):
    monkeypatch.setattr(app_module, "API_REQUIRE_AUTH", True)
    monkeypatch.setattr(app_module, "API_KEY", None)
    monkeypatch.delenv("ATLAS_API_KEY", raising=False)
    monkeypatch.setenv("ATLAS_BUILD_REVISION", "b" * 40)

    response = TestClient(app_module.app).get("/build-info")

    assert response.status_code == 200
    assert response.json() == {"revision": "b" * 40, "status": "known"}
