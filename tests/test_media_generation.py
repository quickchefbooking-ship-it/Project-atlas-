from pathlib import Path

from fastapi.testclient import TestClient

import app as app_module
from app import app
from atlas_media import generate as media


def test_image_generation_uses_local_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(
        media,
        "collect_media_assets",
        lambda *args, **kwargs: {"images": [], "videos": []},
    )
    output = tmp_path / "atlas-local.png"
    result = media.generate_image_from_prompt("a quiet lake at sunrise", str(output))
    assert result == str(output)
    assert output.exists()
    assert output.stat().st_size > 0


def test_image_generation_rejects_empty_prompt(tmp_path):
    try:
        media.generate_image_from_prompt("  ", str(tmp_path / "empty.png"))
    except ValueError:
        return
    raise AssertionError("An empty image prompt must be rejected")


def test_media_health_endpoint():
    response = TestClient(app).get("/media/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_operational_routes_fail_closed_without_api_key(monkeypatch):
    monkeypatch.setattr(app_module, "REQUIRE_AUTH", True)
    monkeypatch.setattr(app_module, "ATLAS_API_KEY", None)
    client = TestClient(app)
    assert client.get("/tasks").status_code == 503
    assert client.post("/media/generate-image", json={"prompt": "test"}).status_code == 503


def test_operational_routes_reject_missing_or_invalid_api_key(monkeypatch):
    monkeypatch.setattr(app_module, "REQUIRE_AUTH", True)
    monkeypatch.setattr(app_module, "ATLAS_API_KEY", "test-secret")
    client = TestClient(app)
    assert client.get("/tasks").status_code == 401
    assert client.get("/tasks", headers={"X-API-Key": "wrong"}).status_code == 401


def test_media_output_path_cannot_escape_output_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "REQUIRE_AUTH", True)
    monkeypatch.setattr(app_module, "ATLAS_API_KEY", "test-secret")
    response = TestClient(app).post(
        "/media/generate-image",
        headers={"X-API-Key": "test-secret"},
        json={"prompt": "test", "output_path": "../outside.png"},
    )
    assert response.status_code == 400
