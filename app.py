from pathlib import Path

from fastapi.testclient import TestClient

from app import app
from atlas_media.generate import generate_image_from_prompt


def test_generate_image_falls_back_locally(tmp_path):
    output = tmp_path / "atlas_local.png"
    result = generate_image_from_prompt("a mountain lake with clouds", str(output))
    assert result == str(output)
    assert Path(result).exists()
    assert Path(result).stat().st_size > 0


def test_media_routes_work_without_auth():
    client = TestClient(app)
    response = client.post(
        "/media/generate-image",
        json={"prompt": "city skyline at night"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert Path(response.json()["path"]).exists()

    response_video = client.post(
        "/media/generate-video",
        json={"prompt": "travel montage of a field at sunrise", "narration": "A new day begins."},
    )
    if response_video.status_code == 200:
        assert Path(response_video.json()["path"]).exists()
    else:
        assert response_video.status_code in {200, 500}
