import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from atlas_engine.conversation_contract import ConversationOutput
from atlas_engine.conversation_service import ConversationService
from atlas_engine.http_identity import require_verified_principal
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.professor_conversation_api import router
from atlas_engine.tenant_conversation_repository import initialize_tenant_conversation_schema


SCOPES = frozenset({
    "conversations:read",
    "conversations:write",
    "conversations:delete",
})


class EchoProvider:
    name = "test-echo"

    def respond(self, conversation):
        last = conversation.messages[-1].content
        return ConversationOutput(
            text=f"Professor received: {last}",
            provider="test-echo",
            model="fixture-v1",
        )


def make_client(tmp_path, principal=None, configured=True):
    db_path = tmp_path / "tenant.sqlite"
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    initialize_tenant_conversation_schema(db)
    db.close()

    app = FastAPI()
    app.state.tenant_data_path = str(db_path)
    app.state.conversation_service = (
        ConversationService(EchoProvider()) if configured else ConversationService()
    )
    identity = principal or RequestPrincipal(
        "https://issuer.example.test", "alice", "tenant-a", True, SCOPES
    )
    app.dependency_overrides[require_verified_principal] = lambda: identity
    app.include_router(router)
    return TestClient(app), db_path


def test_authenticated_conversation_round_trip_persists_server_response(tmp_path):
    client, _db_path = make_client(tmp_path)

    first = client.post("/professor/conversation", json={"message": "Hello"})
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["response"] == "Professor received: Hello"
    conversation_id = first_data["conversation_id"]

    second = client.post(
        "/professor/conversation",
        json={"conversation_id": conversation_id, "message": "What did I say?"},
    )
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id

    history = client.get(f"/professor/conversations/{conversation_id}")
    assert history.status_code == 200
    assert [item["role"] for item in history.json()["messages"]] == [
        "user", "assistant", "user", "assistant"
    ]
    assert history.json()["messages"][0]["content"] == "Hello"


def test_conversation_cannot_be_read_by_another_owner(tmp_path):
    client, _db_path = make_client(tmp_path)
    created = client.post("/professor/conversation", json={"message": "Private"})
    conversation_id = created.json()["conversation_id"]

    other = RequestPrincipal(
        "https://issuer.example.test", "bob", "tenant-a", True, SCOPES
    )
    client.app.dependency_overrides[require_verified_principal] = lambda: other
    response = client.get(f"/professor/conversations/{conversation_id}")
    assert response.status_code == 404


def test_missing_provider_keeps_chat_fail_closed(tmp_path):
    client, db_path = make_client(tmp_path, configured=False)
    response = client.post("/professor/conversation", json={"message": "Hello"})
    assert response.status_code == 503

    db = sqlite3.connect(db_path)
    count = db.execute(
        "SELECT COUNT(*) FROM tenant_professor_conversations"
    ).fetchone()[0]
    db.close()
    assert count == 0


def test_request_cannot_supply_assistant_role_or_extra_fields(tmp_path):
    client, _db_path = make_client(tmp_path)
    response = client.post(
        "/professor/conversation",
        json={"message": "Hello", "role": "assistant"},
    )
    assert response.status_code == 422


def test_conversation_delete_removes_message_content(tmp_path):
    client, db_path = make_client(tmp_path)
    created = client.post("/professor/conversation", json={"message": "Erase this"})
    conversation_id = created.json()["conversation_id"]

    deleted = client.delete(f"/professor/conversations/{conversation_id}")
    assert deleted.status_code == 204
    missing = client.get(f"/professor/conversations/{conversation_id}")
    assert missing.status_code == 404

    db = sqlite3.connect(db_path)
    count = db.execute(
        "SELECT COUNT(*) FROM tenant_professor_conversation_messages"
    ).fetchone()[0]
    db.close()
    assert count == 0
