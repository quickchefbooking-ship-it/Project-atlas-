"""Cross-boundary integration tests for THE PROFESSOR's safe reasoning lifecycle."""
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from atlas_engine.capability_registry import CapabilityDefinition, CapabilityRegistry
from atlas_engine.conversation_contract import ConversationOutput
from atlas_engine.conversation_service import ConversationService
from atlas_engine.http_identity import require_verified_principal
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.plan_contract import PlanStep, ProfessorPlan, RiskClass
from atlas_engine.professor_conversation_api import router as conversation_router
from atlas_engine.professor_evaluation_api import router as evaluation_router
from atlas_engine.professor_lesson_review_api import router as lesson_router
from atlas_engine.professor_reasoning_audit_api import router as audit_router
from atlas_engine.tenant_conversation_repository import initialize_tenant_conversation_schema
from atlas_engine.tenant_evaluation_repository import initialize_tenant_evaluation_schema
from atlas_engine.tenant_lesson_review import initialize_tenant_lesson_review_schema
from atlas_engine.tenant_plan_lifecycle import router as plan_lifecycle_router
from atlas_engine.tenant_plan_repository import TenantPlanRepository, initialize_tenant_plan_schema
from atlas_engine.tenant_reasoning_audit import initialize_reasoning_audit_schema


ALICE_SCOPES = frozenset({
    "conversations:read", "conversations:write", "conversations:delete",
    "evaluations:read", "evaluations:write",
    "lessons:propose", "lessons:read",
    "plans:read", "plans:write", "public.research.read",
})
BOB_SCOPES = frozenset({"lessons:approve", "lessons:read"})


def principal(subject, scopes):
    return RequestPrincipal(
        "https://issuer.example.test", subject, "tenant-integration",
        True, frozenset(scopes),
    )


class FixtureProvider:
    name = "integration-fixture"

    def respond(self, conversation):
        if "structured reasoning decomposition" in conversation.messages[-1].content.lower():
            text = '{"steps":[{"step_id":"research","objective":"Frame the research request"}]}'
        else:
            text = "Research this safely. The research is bounded and no external actions were taken."
        return ConversationOutput(
            text=text,
            provider=self.name,
            model="fixture-v1",
        )


def make_lifecycle_client(tmp_path):
    database_path = tmp_path / "professor-lifecycle.sqlite"
    db = sqlite3.connect(database_path)
    db.row_factory = sqlite3.Row
    initialize_tenant_conversation_schema(db)
    initialize_reasoning_audit_schema(db)
    initialize_tenant_evaluation_schema(db)
    initialize_tenant_lesson_review_schema(db)
    initialize_tenant_plan_schema(db)

    alice = principal("alice", ALICE_SCOPES)
    plan = ProfessorPlan(
        "lifecycle-plan",
        "Research a question safely",
        ("Return a sourced summary",),
        (PlanStep(
            "lookup", "research.lookup", "Find public sources",
            RiskClass.READ_ONLY,
            required_scopes=("public.research.read",),
            capability_version="1",
        ),),
    )
    TenantPlanRepository(db, alice).create(plan)
    db.close()

    registry = CapabilityRegistry([CapabilityDefinition(
        name="research.lookup",
        version="1",
        risk_class="read_only",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
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
    )])

    app = FastAPI()
    app.state.tenant_data_path = str(database_path)
    app.state.tenant_capability_registry = registry
    app.state.conversation_service = ConversationService(FixtureProvider())
    current = {"principal": alice}
    app.dependency_overrides[require_verified_principal] = lambda: current["principal"]
    app.include_router(conversation_router)
    app.include_router(audit_router)
    app.include_router(evaluation_router)
    app.include_router(lesson_router)
    app.include_router(plan_lifecycle_router)
    return TestClient(app), database_path, current


def test_professor_lifecycle_keeps_preview_feedback_and_lessons_separate(tmp_path):
    client, database_path, current = make_lifecycle_client(tmp_path)

    # A plan can be inspected without changing its DRAFT state or enabling execution.
    preview = client.get("/professor/tenant/plans/lifecycle-plan/preview")
    assert preview.status_code == 200
    assert preview.json()["mutated"] is False
    assert preview.json()["execution_enabled"] is False
    db = sqlite3.connect(database_path)
    assert db.execute(
        "SELECT state FROM tenant_professor_plans WHERE plan_id='lifecycle-plan'"
    ).fetchone()[0] == "draft"
    db.close()

    # A successful conversation creates an auditable record.
    turn = client.post("/professor/conversation", json={"message": "Research this safely"})
    assert turn.status_code == 200
    conversation_id = turn.json()["conversation_id"]
    assert turn.json()["audit_id"]

    # Feedback is explicit and remains human-review evidence.
    feedback = client.post("/professor/tenant/evaluations", json={
        "subject_type": "conversation",
        "subject_id": conversation_id,
        "outcome": "helpful",
        "rating": 5,
        "note": "The answer was clear.",
    })
    assert feedback.status_code == 201
    evaluation_id = feedback.json()["evaluation_id"]
    assert "human review only" in feedback.json()["learning_policy"]

    # A lesson is a human-authored proposal and requires a different reviewer.
    proposal = client.post("/professor/tenant/lessons", json={
        "title": "Keep research bounded",
        "lesson_text": "Use approved public evidence and keep execution disabled.",
        "evaluation_ids": [evaluation_id],
    })
    assert proposal.status_code == 201
    candidate_id = proposal.json()["candidate_id"]
    self_review = client.post(
        f"/professor/tenant/lessons/{candidate_id}/decision",
        json={"decision": "approved", "rationale": "Self-review is not permitted."},
    )
    assert self_review.status_code == 403

    current["principal"] = principal("bob", BOB_SCOPES)
    reviewer_view = client.get("/professor/tenant/lessons")
    assert reviewer_view.status_code == 200
    assert reviewer_view.json()["lessons"][0]["status"] == "pending"
    decision = client.post(
        f"/professor/tenant/lessons/{candidate_id}/decision",
        json={"decision": "approved", "rationale": "Reviewed independently."},
    )
    assert decision.status_code == 200
    assert decision.json()["runtime_promotion"] == "disabled"

    # Reviewer identity cannot read the proposer's private conversation or trace.
    # Bob has no conversation-read scope, so access is denied before the API
    # reveals whether the other user private conversation exists.
    assert client.get(f"/professor/conversations/{conversation_id}").status_code == 403
    assert client.get(f"/professor/conversations/{conversation_id}/trace").status_code == 403

    # The owner can inspect the complete read-only trace after switching back.
    current["principal"] = principal("alice", ALICE_SCOPES)
    trace = client.get(f"/professor/conversations/{conversation_id}/trace")
    assert trace.status_code == 200
    payload = trace.json()
    assert len(payload["reasoning_audit"]) == 1
    trace_metadata = payload["reasoning_audit"][0]["metadata"]
    assert trace_metadata["status"] == "ready"
    assert trace_metadata["step_count"] == 1
    assert trace_metadata["critique_accepted"] is True
    assert trace_metadata["execution_enabled"] is False
    assert payload["audit_verification"]["valid"] is True
    assert payload["evaluations"][0]["evaluation_id"] == evaluation_id
    assert payload["learning_policy"].startswith("Feedback is review evidence only")
    assert payload["execution_enabled"] is False
