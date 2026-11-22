import sqlite3
from fastapi import FastAPI
from fastapi.testclient import TestClient
from atlas_engine.http_identity import require_verified_principal
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.professor_lesson_review_api import router
from atlas_engine.tenant_conversation_repository import initialize_tenant_conversation_schema
from atlas_engine.tenant_evaluation_repository import TenantEvaluationRepository,initialize_tenant_evaluation_schema
from atlas_engine.tenant_lesson_review import initialize_tenant_lesson_review_schema
from atlas_engine.tenant_professor_memory import initialize_tenant_memory_schema, TenantProfessorMemoryRepository

def principal(subject,scopes):
    return RequestPrincipal("https://issuer.example",subject,"tenant-a",True,frozenset(scopes))

def make_client(tmp_path,who,scopes):
    path=tmp_path/"tenant.sqlite"
    db=sqlite3.connect(path); db.row_factory=sqlite3.Row
    initialize_tenant_conversation_schema(db); initialize_tenant_evaluation_schema(db); initialize_tenant_lesson_review_schema(db); initialize_tenant_memory_schema(db)
    if who=="alice":
        TenantEvaluationRepository(db,principal("alice",{"evaluations:write"})).record(subject_type="conversation",subject_id="c1",outcome="helpful")
    db.close()
    app=FastAPI(); app.state.tenant_data_path=str(path)
    app.dependency_overrides[require_verified_principal]=lambda:principal(who,scopes)
    app.include_router(router)
    return TestClient(app)

def test_lesson_proposal_and_independent_review_api(tmp_path):
    proposer=make_client(tmp_path,"alice",{"lessons:propose","lessons:read"})
    created=proposer.post("/professor/tenant/lessons",json={"title":"Concise answers","lesson_text":"Use concise steps for procedural requests.","evaluation_ids":[1]})
    assert created.status_code==201
    candidate=created.json()["candidate_id"]
    assert created.json()["runtime_promotion"]=="disabled"
    assert proposer.post(f"/professor/tenant/lessons/{candidate}/decision",json={"decision":"approved"}).status_code==403
    reviewer=make_client(tmp_path,"bob",{"lessons:approve","lessons:read"})
    decision=reviewer.post(f"/professor/tenant/lessons/{candidate}/decision",json={"decision":"approved","rationale":"Reviewed"})
    assert decision.status_code==200
    assert decision.json()["status"]=="approved"
    assert decision.json()["runtime_promotion"]=="disabled"
    assert reviewer.get("/professor/tenant/lessons").json()["lessons"][0]["status"]=="approved"

def test_lesson_api_rejects_unowned_evidence(tmp_path):
    proposer=make_client(tmp_path,"bob",{"lessons:propose"})
    response=proposer.post("/professor/tenant/lessons",json={"title":"x","lesson_text":"y","evaluation_ids":[1]})
    assert response.status_code==404

def test_approved_owned_lesson_creates_pending_memory_then_requires_second_approval(tmp_path):
    owner_scopes={"lessons:propose","lessons:read","memory:propose","memory:read","memory:approve"}
    owner=make_client(tmp_path,"alice",owner_scopes)
    created=owner.post("/professor/tenant/lessons",json={
        "title":"Concise answers",
        "lesson_text":"Use concise steps for procedural requests.",
        "evaluation_ids":[1],
    })
    candidate_id=created.json()["candidate_id"]

    reviewer=make_client(tmp_path,"bob",{"lessons:approve","lessons:read"})
    approved=reviewer.post(f"/professor/tenant/lessons/{candidate_id}/decision",json={
        "decision":"approved","rationale":"Evidence supports this feedback.",
    })
    assert approved.status_code==200

    converted=owner.post(f"/professor/tenant/lessons/{candidate_id}/memory-proposal",json={"retention_days":30})
    assert converted.status_code==201
    payload=converted.json()
    assert payload["status"]=="pending"
    assert payload["approval_required"] is True
    assert payload["idempotent"] is False

    db=sqlite3.connect(tmp_path/"tenant.sqlite"); db.row_factory=sqlite3.Row
    alice=principal("alice",owner_scopes)
    memory=TenantProfessorMemoryRepository(db,alice)
    assert memory.retrieve("concise steps") == ()
    repeated=owner.post(f"/professor/tenant/lessons/{candidate_id}/memory-proposal",json={"retention_days":30})
    assert repeated.status_code==201
    assert repeated.json()["proposal_id"]==payload["proposal_id"]
    assert repeated.json()["idempotent"] is True
    memory.decide(payload["proposal_id"],decision="approved",rationale="Owner explicitly approved for memory.")
    assert len(memory.retrieve("concise steps"))==1
    db.close()


def test_pending_lesson_cannot_be_converted_to_memory(tmp_path):
    owner=make_client(tmp_path,"alice",{"lessons:propose","lessons:read","memory:propose"})
    created=owner.post("/professor/tenant/lessons",json={
        "title":"Pending","lesson_text":"Not reviewed yet.","evaluation_ids":[1],
    })
    candidate_id=created.json()["candidate_id"]
    response=owner.post(f"/professor/tenant/lessons/{candidate_id}/memory-proposal",json={})
    assert response.status_code==409
    assert "Only approved" in response.json()["detail"]


def test_owner_cannot_promote_another_users_lesson_candidate(tmp_path):
    owner=make_client(tmp_path,"alice",{"lessons:propose","lessons:read","memory:propose"})
    candidate_id=owner.post("/professor/tenant/lessons",json={
        "title":"Private","lesson_text":"Owner scoped.","evaluation_ids":[1],
    }).json()["candidate_id"]
    other=make_client(tmp_path,"bob",{"lessons:read","memory:propose"})
    response=other.post(f"/professor/tenant/lessons/{candidate_id}/memory-proposal",json={})
    assert response.status_code==404
