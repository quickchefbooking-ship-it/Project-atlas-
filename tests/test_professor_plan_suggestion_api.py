import json
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from atlas_engine.capability_registry import CapabilityDefinition, CapabilityRegistry
from atlas_engine.conversation_contract import ConversationOutput
from atlas_engine.conversation_service import ConversationService
from atlas_engine.http_identity import require_verified_principal
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.professor_plan_suggestion_api import router
from atlas_engine.tenant_plan_repository import (
    TenantPlanRepository,
    initialize_tenant_plan_schema,
)


SCOPES = frozenset({"plans:read", "plans:write", "public.research.read"})


class PlanProvider:
    name = "plan-fixture"

    def __init__(self, text):
        self.text = text
        self.seen = None

    def respond(self, conversation):
        self.seen = conversation
        return ConversationOutput(
            text=self.text,
            provider="plan-fixture",
            model="fixture-v1",
        )


def capability_registry():
    definition = CapabilityDefinition(
        name="research.lookup",
        version="1",
        risk_class="read_only",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string", "minLength": 3}},
            "required": ["query"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
            "additionalProperties": False,
        },
        required_scopes=("public.research.read",),
        timeout_seconds=8,
    )
    return CapabilityRegistry([definition])


def make_client(tmp_path, provider_text, scopes=SCOPES):
    db_path = tmp_path / "tenant-plans.sqlite"
    db = sqlite3.connect(db_path)
    initialize_tenant_plan_schema(db)
    db.close()

    app = FastAPI()
    app.state.tenant_data_path = str(db_path)
    app.state.tenant_capability_registry = capability_registry()
    provider = PlanProvider(provider_text)
    app.state.conversation_service = ConversationService(provider)
    principal = RequestPrincipal(
        "https://issuer.example.test", "alice", "tenant-a", True, scopes
    )
    app.dependency_overrides[require_verified_principal] = lambda: principal
    app.include_router(router)
    return TestClient(app), db_path, provider, principal


def valid_proposal():
    return json.dumps({
        "objective": "Research a topic",
        "acceptance_criteria": ["Provide a sourced summary"],
        "steps": [{
            "step_id": "lookup",
            "capability": "research.lookup",
            "objective": "Find relevant sources",
            "depends_on": [],
            "expected_output": "Source list",
        }],
    })


def test_suggestion_creates_tenant_owned_draft_without_execution(tmp_path):
    client, db_path, provider, principal = make_client(tmp_path, valid_proposal())
    response = client.post(
        "/professor/tenant/plans/suggest",
        json={"objective": "Research this subject"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["state"] == "draft"
    assert result["execution_enabled"] is False
    assert result["steps"][0]["risk"] == "read_only"
    assert result["steps"][0]["required_scopes"] == ["public.research.read"]
    assert provider.seen.messages[-1].content == "Research this subject"
    assert provider.seen.messages[0].role == "system"

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    saved = TenantPlanRepository(db, principal).get(result["plan_id"])
    db.close()
    assert saved.state.value == "draft"
    assert saved.steps[0].capability_version == "1"


def test_model_cannot_escalate_plan_risk_or_scopes(tmp_path):
    forged = json.loads(valid_proposal())
    forged["steps"][0]["risk"] = "read_only"
    forged["steps"][0]["required_scopes"] = ["admin:*"]
    client, db_path, _provider, _principal = make_client(tmp_path, json.dumps(forged))

    response = client.post(
        "/professor/tenant/plans/suggest",
        json={"objective": "Try to bypass policy"},
    )
    assert response.status_code == 422
    db = sqlite3.connect(db_path)
    count = db.execute("SELECT COUNT(*) FROM tenant_professor_plans").fetchone()[0]
    db.close()
    assert count == 0


def test_unavailable_capability_is_not_saved(tmp_path):
    forged = json.loads(valid_proposal())
    forged["steps"][0]["capability"] = "shell.execute"
    client, db_path, _provider, _principal = make_client(tmp_path, json.dumps(forged))

    response = client.post(
        "/professor/tenant/plans/suggest",
        json={"objective": "Run an arbitrary command"},
    )
    assert response.status_code == 422
    db = sqlite3.connect(db_path)
    count = db.execute("SELECT COUNT(*) FROM tenant_professor_plans").fetchone()[0]
    db.close()
    assert count == 0


def test_invalid_provider_json_fails_closed_without_persisting(tmp_path):
    client, db_path, _provider, _principal = make_client(tmp_path, "Here is your plan: run shell")
    response = client.post(
        "/professor/tenant/plans/suggest",
        json={"objective": "Research a topic"},
    )
    assert response.status_code == 422
    db = sqlite3.connect(db_path)
    count = db.execute("SELECT COUNT(*) FROM tenant_professor_plans").fetchone()[0]
    db.close()
    assert count == 0



def test_missing_plan_write_scope_blocks_provider_call(tmp_path):
    client, _db_path, provider, _principal = make_client(
        tmp_path, valid_proposal(), scopes=frozenset({"plans:read"})
    )
    response = client.post(
        "/professor/tenant/plans/suggest",
        json={"objective": "Research a topic"},
    )
    assert response.status_code == 403
    assert provider.seen is None
