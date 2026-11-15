from fastapi.testclient import TestClient

import app as professor_app
from atlas_engine.identity_policy import RequestPrincipal


TEST_PRINCIPAL = RequestPrincipal(
    "https://issuer.example.test", "voice-test-user", "voice-test-tenant", True,
    frozenset({"conversations:read", "conversations:write", "conversations:delete"}),
)


def _authenticated_test_client():
    professor_app.app.dependency_overrides[professor_app.require_verified_principal] = lambda: TEST_PRINCIPAL
    return TestClient(professor_app.app)


def _clear_overrides():
    professor_app.app.dependency_overrides.pop(professor_app.require_verified_principal, None)
    professor_app.app.dependency_overrides.pop(professor_app.require_api_key, None)


def test_professor_voice_page_is_served():
    response = TestClient(professor_app.app).get("/professor/voice")
    assert response.status_code == 200
    assert "Talk to Professor" in response.text
    assert "Start listening" in response.text
    assert "Test Professor's voice" in response.text


def test_conversation_endpoint_fails_closed_until_reasoning_backend_exists():
    professor_app.app.dependency_overrides[professor_app.require_api_key] = lambda: True
    try:
        response = _authenticated_test_client().post(
            "/professor/conversation",
            json={"message": "Hello Professor"},
        )
    finally:
        _clear_overrides()

    assert response.status_code == 503
    assert "conversational reasoning service is not configured" in response.json()["detail"]


def test_conversation_endpoint_rejects_empty_or_oversized_messages():
    try:
        client = _authenticated_test_client()
        empty = client.post("/professor/conversation", json={"message": ""})
        oversized = client.post("/professor/conversation", json={"message": "x" * 4001})
    finally:
        _clear_overrides()

    assert empty.status_code == 422
    assert oversized.status_code == 422
