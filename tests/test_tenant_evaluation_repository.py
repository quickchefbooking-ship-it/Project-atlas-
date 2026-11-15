import sqlite3

import pytest

from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.tenant_evaluation_repository import (
    TenantEvaluationRepository,
    initialize_tenant_evaluation_schema,
)


SCOPES = frozenset({"evaluations:read", "evaluations:write"})


def principal(subject="alice", tenant="tenant-a", scopes=SCOPES):
    return RequestPrincipal("https://issuer.example", subject, tenant, True, scopes)


def make_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    initialize_tenant_evaluation_schema(db)
    return db


def test_records_and_reads_evaluation_with_provenance():
    db = make_db()
    repository = TenantEvaluationRepository(db, principal())
    record = repository.record(
        subject_type="conversation", subject_id="conv-1",
        outcome="helpful", rating=5, note="Clear answer",
        evidence=[{"document_id": "doc-1", "url": "https://example.org/source",
                   "content_sha256": "a" * 64}],
    )
    assert record.rating == 5
    assert record.evidence[0]["document_id"] == "doc-1"
    assert repository.list()[0].note == "Clear answer"


def test_evaluations_are_isolated_by_tenant_and_owner():
    db = make_db()
    TenantEvaluationRepository(db, principal()).record(
        subject_type="task", subject_id="task-1", outcome="successful"
    )
    assert TenantEvaluationRepository(db, principal("bob")).list() == ()
    assert TenantEvaluationRepository(db, principal("alice", "tenant-b")).list() == ()


def test_evaluation_requires_explicit_scope():
    db = make_db()
    repository = TenantEvaluationRepository(
        db, principal(scopes=frozenset({"evaluations:read"}))
    )
    with pytest.raises(PermissionError):
        repository.record(subject_type="task", subject_id="t1", outcome="successful")


@pytest.mark.parametrize("kwargs", [
    {"subject_type": "unknown", "subject_id": "x", "outcome": "successful"},
    {"subject_type": "task", "subject_id": "x", "outcome": "made_up"},
    {"subject_type": "task", "subject_id": "x", "outcome": "successful", "rating": True},
    {"subject_type": "task", "subject_id": "x", "outcome": "successful", "note": "x" * 2001},
    {"subject_type": "task", "subject_id": "x", "outcome": "successful",
     "evidence": [{"document_id": "x", "unexpected": "value"}]},
])
def test_rejects_invalid_evaluation_payload(kwargs):
    db = make_db()
    with pytest.raises(ValueError):
        TenantEvaluationRepository(db, principal()).record(**kwargs)


def test_evaluation_history_is_append_only():
    db = make_db()
    record = TenantEvaluationRepository(db, principal()).record(
        subject_type="task", subject_id="task-1", outcome="successful"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE tenant_professor_evaluations SET note='changed' WHERE evaluation_id=?",
                   (record.evaluation_id,))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM tenant_professor_evaluations WHERE evaluation_id=?",
                   (record.evaluation_id,))
