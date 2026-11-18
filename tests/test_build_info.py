from fastapi.testclient import TestClient

from app import app


def test_build_info_reports_full_valid_deployment_revision(monkeypatch):
    monkeypatch.setenv("ATLAS_BUILD_REVISION", "A" * 40)
    monkeypatch.setenv("GITHUB_SHA", "b" * 40)

    response = TestClient(app).get("/build-info")

    assert response.status_code == 200
    assert response.json() == {
        "service": "AtlasOnePro",
        "revision": "a" * 40,
        "revision_available": True,
        "revision_source": "ATLAS_BUILD_REVISION",
    }


def test_build_info_falls_back_to_github_sha(monkeypatch):
    monkeypatch.setenv("ATLAS_BUILD_REVISION", "not-a-sha")
    monkeypatch.setenv("GITHUB_SHA", "B" * 40)

    response = TestClient(app).get("/build-info")

    assert response.status_code == 200
    assert response.json()["revision"] == "b" * 40
    assert response.json()["revision_source"] == "GITHUB_SHA"


def test_build_info_does_not_claim_unknown_or_malformed_revision(monkeypatch):
    monkeypatch.setenv("ATLAS_BUILD_REVISION", "short")
    monkeypatch.setenv("GITHUB_SHA", "z" * 40)

    response = TestClient(app).get("/build-info")

    assert response.status_code == 200
    assert response.json() == {
        "service": "AtlasOnePro",
        "revision": None,
        "revision_available": False,
        "revision_source": None,
    }
