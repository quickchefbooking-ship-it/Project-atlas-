"""End-to-end browser-session to Professor conversation composition tests."""

import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from atlas_engine.account_identity import SQLiteAccountRepository
from atlas_engine.atlas_session_identity import AtlasSessionIdentityService, ATLAS_IDENTITY_ISSUER
from atlas_engine.conversation_contract import ConversationOutput
from atlas_engine.conversation_service import ConversationService
from atlas_engine.http_identity import ATLAS_CSRF_HEADER, ATLAS_SESSION_COOKIE
from atlas_engine.professor_conversation_api import router as conversation_router
from atlas_engine.session_identity import SQLiteSessionRepository
from atlas_engine.tenant_conversation_repository import initialize_tenant_conversation_schema
from atlas_engine.tenant_membership import SQLiteMembershipRegistry
from atlas_engine.tenant_reasoning_audit import initialize_reasoning_audit_schema
from atlas_engine.tenant_professor_memory import initialize_tenant_memory_schema


TRUSTED_ORIGIN = "https://atlas.example.test"


class IntegrationProvider:
    name = "session-integration"

    def respond(self, conversation):
        latest = conversation.messages[-1].content
        if "decomposition now" in latest.lower():
            answer = '{"steps":[{"step_id":"answer","objective":"Answer the user"}]}'
        else:
            answer = f"Professor received: {latest}"
        return ConversationOutput(
            text=answer,
            provider=self.name,
            model="integration-fixture",
        )


def test_real_browser_session_reaches_tenant_scoped_professor_conversation(tmp_path, monkeypatch):
    from atlas_engine import professor_reasoning_context

    # Isolate the browser-session boundary; evidence formatting is tested separately.
    monkeypatch.setattr(professor_reasoning_context, "build_reasoning_evidence", lambda query, limit: [])
    identity_path = str(tmp_path / "atlas-identity.sqlite")
    accounts = SQLiteAccountRepository(identity_path)
    accounts.initialize()
    account = accounts.create_pending_account(
        "professor-browser@example.test", "a sufficiently long integration password"
    )
    accounts.set_account_status(account.account_id, "active")

    sessions = SQLiteSessionRepository(identity_path)
    sessions.initialize()
    memberships = SQLiteMembershipRegistry(str(tmp_path / "memberships.sqlite"))
    memberships.initialize()
    memberships.create_tenant("company-a", "Company A")
    memberships.provision_membership(
        ATLAS_IDENTITY_ISSUER,
        account.account_id,
        "company-a",
        {"conversations:read", "conversations:write", "memory:read", "professor:chat"},
    )
    identity_service = AtlasSessionIdentityService(sessions, memberships)
    issued = sessions.issue_session(account.account_id)
    csrf = sessions.issue_csrf_token(issued.token)

    tenant_path = str(tmp_path / "tenant.sqlite")
    db = sqlite3.connect(tenant_path)
    db.row_factory = sqlite3.Row
    initialize_tenant_conversation_schema(db)
    initialize_reasoning_audit_schema(db)
    initialize_tenant_memory_schema(db)
    db.close()

    app = FastAPI()
    app.state.atlas_session_identity_service = identity_service
    app.state.atlas_trusted_origins = frozenset({TRUSTED_ORIGIN})
    app.state.tenant_data_path = tenant_path
    app.state.conversation_service = ConversationService(IntegrationProvider())
    app.include_router(conversation_router)

    client = TestClient(app)
    browser_headers = {
        "Origin": TRUSTED_ORIGIN,
        "Sec-Fetch-Site": "same-origin",
        ATLAS_CSRF_HEADER: csrf,
        "Cookie": f"{ATLAS_SESSION_COOKIE}={issued.token}",
    }
    response = client.post(
        "/professor/conversation",
        json={"message": "Help me plan the next AtlasOnePro build step."},
        headers=browser_headers,
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["response"] == (
        "Professor received: Help me plan the next AtlasOnePro build step."
    )
    assert result["execution_enabled"] is False
    assert result["memory_references"] == []

    history = client.get(
        f"/professor/conversations/{result['conversation_id']}",
        headers={"Cookie": f"{ATLAS_SESSION_COOKIE}={issued.token}"},
    )
    assert history.status_code == 200, history.text
    assert [message["role"] for message in history.json()["messages"]] == [
        "user", "assistant"
    ]
    assert history.json()["messages"][0]["content"] == (
        "Help me plan the next AtlasOnePro build step."
    )
