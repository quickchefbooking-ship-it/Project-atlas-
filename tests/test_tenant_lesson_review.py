import sqlite3
import pytest
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.tenant_evaluation_repository import TenantEvaluationRepository,initialize_tenant_evaluation_schema
from atlas_engine.tenant_lesson_review import TenantLessonReviewRepository,initialize_tenant_lesson_review_schema

def principal(subject,scopes):
    return RequestPrincipal("https://issuer.example",subject,"tenant-a",True,frozenset(scopes))

def database():
    db=sqlite3.connect(":memory:")
    db.row_factory=sqlite3.Row
    initialize_tenant_evaluation_schema(db)
    initialize_tenant_lesson_review_schema(db)
    return db

def test_lesson_requires_owned_evidence_and_independent_reviewer():
    db=database()
    proposer=principal("alice",{"evaluations:write","lessons:propose","lessons:read"})
    evaluation=TenantEvaluationRepository(db,proposer).record(subject_type="conversation",subject_id="c1",outcome="helpful")
    repo=TenantLessonReviewRepository(db,proposer)
    candidate=repo.propose(title="Use concise steps",lesson_text="Prefer short numbered steps when the request is procedural.",evaluation_ids=[evaluation.evaluation_id])
    assert repo.list()[0]["status"]=="pending"
    with pytest.raises(PermissionError):
        repo.decide(candidate,decision="approved")
    reviewer=TenantLessonReviewRepository(db,principal("bob",{"lessons:approve","lessons:read"}))
    assert reviewer.list()[0]["candidate_id"]==candidate
    assert reviewer.decide(candidate,decision="approved",rationale="Reviewed against feedback.")=="approved"
    assert reviewer.list()[0]["status"]=="approved"
    assert reviewer.list()[0]["runtime_promotion"]=="disabled"
    with pytest.raises(ValueError):
        reviewer.decide(candidate,decision="rejected")

def test_lesson_cannot_reference_another_owners_evaluation():
    db=database()
    alice=principal("alice",{"evaluations:write","lessons:propose"})
    record=TenantEvaluationRepository(db,alice).record(subject_type="conversation",subject_id="c1",outcome="helpful")
    bob=TenantLessonReviewRepository(db,principal("bob",{"lessons:propose"}))
    with pytest.raises(LookupError):
        bob.propose(title="No",lesson_text="No",evaluation_ids=[record.evaluation_id])

def test_lesson_candidate_and_decisions_are_append_only():
    db=database()
    p=principal("alice",{"evaluations:write","lessons:propose"})
    record=TenantEvaluationRepository(db,p).record(subject_type="conversation",subject_id="c1",outcome="helpful")
    candidate=TenantLessonReviewRepository(db,p).propose(title="A",lesson_text="B",evaluation_ids=[record.evaluation_id])
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE tenant_lesson_candidates SET title='changed' WHERE candidate_id=?",(candidate,))
