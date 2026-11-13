from fastapi.testclient import TestClient

from app import app
from atlas_media import generate as media


def test_image_generation_uses_local_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(
        media,
        "collect_media_assets",
        lambda *args, **kwargs: {"images": [], "videos": []},
    )
    output = tmp_path / "atlas-local.png"
    result = media.generate_image_from_prompt("a quiet lake at sunrise", str(output))
    assert result == str(output.resolve())
    assert output.exists()
    assert output.stat().st_size > 0


def test_image_generation_rejects_empty_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    try:
        media.generate_image_from_prompt("  ", str(tmp_path / "empty.png"))
    except ValueError:
        return
    raise AssertionError("An empty image prompt must be rejected")


def test_image_generation_rejects_output_path_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path / "safe-output")
    outside = tmp_path / "outside.png"
    try:
        media.generate_image_from_prompt("a test image", str(outside))
    except ValueError as exc:
        assert "inside" in str(exc)
        return
    raise AssertionError("Output paths outside the media directory must be rejected")


def test_media_health_endpoint():
    response = TestClient(app).get("/media/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
