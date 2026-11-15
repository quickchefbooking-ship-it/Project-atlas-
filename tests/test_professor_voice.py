from fastapi.testclient import TestClient

import app as professor_app


def test_professor_voice_page_is_served():
    response = TestClient(professor_app.app).get("/professor/voice")
    assert response.status_code == 200
    assert "Talk to Professor" in response.text
    assert "Start listening" in response.text
    assert "Test Professor's voice" in response.text


def test_conversation_endpoint_fails_closed_until_reasoning_backend_exists():
    professor_app.app.dependency_overrides[professor_app.require_api_key] = lambda: True
    try:
        response = TestClient(professor_app.app).post(
            "/professor/conversation",
            json={"message": "Hello Professor"},
        )
    finally:
        professor_app.app.dependency_overrides.pop(professor_app.require_api_key, None)

    assert response.status_code == 503
    assert "conversational reasoning service is not configured" in response.json()["detail"]


def test_conversation_endpoint_rejects_empty_or_oversized_messages():
    professor_app.app.dependency_overrides[professor_app.require_api_key] = lambda: True
    try:
        client = TestClient(professor_app.app)
        empty = client.post("/professor/conversation", json={"message": ""})
        oversized = client.post("/professor/conversation", json={"message": "x" * 4001})
    finally:
        professor_app.app.dependency_overrides.pop(professor_app.require_api_key, None)

    assert empty.status_code == 422
    assert oversized.status_code == 422
