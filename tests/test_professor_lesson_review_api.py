import sqlite3
from fastapi import FastAPI
from fastapi.testclient import TestClient
from atlas_engine.http_identity import require_verified_principal
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.professor_lesson_review_api import router
from atlas_engine.tenant_conversation_repository import initialize_tenant_conversation_schema
from atlas_engine.tenant_evaluation_repository import TenantEvaluationRepository,initialize_tenant_evaluation_schema
from atlas_engine.tenant_lesson_review import initialize_tenant_lesson_review_schema

def principal(subject,scopes):
    return RequestPrincipal("https://issuer.example",subject,"tenant-a",True,frozenset(scopes))

def make_client(tmp_path,who,scopes):
    path=tmp_path/"tenant.sqlite"
    db=sqlite3.connect(path); db.row_factory=sqlite3.Row
    initialize_tenant_conversation_schema(db); initialize_tenant_evaluation_schema(db); initialize_tenant_lesson_review_schema(db)
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
