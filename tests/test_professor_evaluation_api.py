import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from atlas_engine.http_identity import require_verified_principal
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.professor_evaluation_api import router
from atlas_engine.tenant_conversation_repository import (
    TenantConversationRepository, initialize_tenant_conversation_schema,
)
from atlas_engine.tenant_evaluation_repository import initialize_tenant_evaluation_schema
from atlas_engine.tenant_lesson_review import initialize_tenant_lesson_review_schema, TenantLessonReviewRepository


def make_client(tmp_path):
    path = tmp_path / "tenant.sqlite"
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    initialize_tenant_conversation_schema(db)
    initialize_tenant_evaluation_schema(db)
    principal = RequestPrincipal(
        "https://issuer.example", "alice", "tenant-a", True,
        frozenset({"conversations:read", "conversations:write", "evaluations:read", "evaluations:write", "lessons:propose", "lessons:read"}),
    )
    initialize_tenant_lesson_review_schema(db)
    TenantConversationRepository(db, principal).create("conv-1")
    db.close()
    app = FastAPI()
    app.state.tenant_data_path = str(path)
    app.dependency_overrides[require_verified_principal] = lambda: principal
    app.include_router(router)
    return TestClient(app)


def test_authenticated_evaluation_api_records_and_lists_feedback(tmp_path):
    client = make_client(tmp_path)
    created = client.post("/professor/tenant/evaluations", json={
        "subject_type": "conversation", "subject_id": "conv-1",
        "outcome": "helpful", "rating": 5, "note": "Useful and sourced",
        "evidence": [{"document_id": "doc-1", "url": "https://example.org/a-long-source-path"}],
    })
    assert created.status_code == 201
    assert created.json()["learning_policy"].startswith("Stored for human review")
    listed = client.get("/professor/tenant/evaluations")
    assert listed.status_code == 200
    assert listed.json()["evaluations"][0]["note"] == "Useful and sourced"


def test_evaluation_api_rejects_unknown_or_unowned_conversation(tmp_path):
    client = make_client(tmp_path)
    response = client.post("/professor/tenant/evaluations", json={
        "subject_type": "conversation", "subject_id": "not-owned",
        "outcome": "helpful",
    })
    assert response.status_code == 404



def test_evaluation_summary_returns_only_aggregate_feedback(tmp_path):
    client = make_client(tmp_path)
    client.post("/professor/tenant/evaluations", json={
        "subject_type": "conversation", "subject_id": "conv-1",
        "outcome": "helpful", "rating": 4, "note": "Do not expose this note",
    })
    response = client.get("/professor/tenant/evaluations/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["outcomes"]["helpful"] == 1
    assert payload["average_rating"] == 4.0
    assert "Do not expose this note" not in response.text

def test_negative_explicit_feedback_creates_pending_review_candidate(tmp_path):
    client = make_client(tmp_path)
    created = client.post("/professor/tenant/evaluations", json={
        "subject_type": "conversation", "subject_id": "conv-1",
        "outcome": "not_helpful", "rating": 1,
        "note": "The response missed the requested practical steps.",
    })
    assert created.status_code == 201
    payload = created.json()
    assert payload["learning_candidate"]["status"] == "pending"
    assert payload["learning_candidate"]["runtime_promotion"] == "disabled"
    assert payload["learning_candidate"]["review_required"] == "independent reviewer"

    db = sqlite3.connect(tmp_path / "tenant.sqlite")
    db.row_factory = sqlite3.Row
    reader = RequestPrincipal(
        "https://issuer.example", "alice", "tenant-a", True,
        frozenset({"lessons:read"}),
    )
    candidate = TenantLessonReviewRepository(db, reader).list()[0]
    assert candidate["status"] == "pending"
    assert payload["evaluation_id"] in candidate["evaluation_ids"]
    assert "missed the requested practical steps" in candidate["lesson_text"]
    db.close()


def test_positive_feedback_does_not_auto_create_lesson_candidate(tmp_path):
    client = make_client(tmp_path)
    created = client.post("/professor/tenant/evaluations", json={
        "subject_type": "conversation", "subject_id": "conv-1",
        "outcome": "helpful", "rating": 5, "note": "Clear and useful.",
    })
    assert created.status_code == 201
    assert created.json()["learning_candidate"] is None
    db = sqlite3.connect(tmp_path / "tenant.sqlite")
    assert db.execute("SELECT COUNT(*) FROM tenant_lesson_candidates").fetchone()[0] == 0
    db.close()
