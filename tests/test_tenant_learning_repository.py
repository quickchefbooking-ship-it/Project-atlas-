import sqlite3

import pytest

from atlas_engine.identity_policy import AuthorizationDenied, RequestPrincipal
from atlas_engine.tenant_repository_prototype import initialize_prototype_schema, TenantTaskRepository, TenantTaskNotFound
from atlas_engine.tenant_learning_repository import initialize_learning_schema, TenantLearningRepository


def principal(tenant, scopes=None):
    return RequestPrincipal(
        issuer="https://issuer.example.test/",
        subject=f"user-{tenant}",
        tenant_id=tenant,
        membership_active=True,
        scopes=frozenset(scopes or {
            "tasks:read", "tasks:write",
            "evaluations:read", "evaluations:write",
            "lessons:read", "lessons:write",
            "proposals:read", "proposals:write",
        }),
    )


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_prototype_schema(conn)
    initialize_learning_schema(conn)
    yield conn
    conn.close()


def test_learning_records_are_separated_by_tenant(db):
    tasks_a = TenantTaskRepository(db, principal("a"))
    tasks_b = TenantTaskRepository(db, principal("b"))
    learning_a = TenantLearningRepository(db, principal("a"))
    learning_b = TenantLearningRepository(db, principal("b"))
    task_a = tasks_a.create_task("A task")
    task_b = tasks_b.create_task("B task")

    learning_a.add_evaluation("eval-a", task_a, True, 0.95, ["passed"])
    learning_b.add_evaluation("eval-b", task_b, False, 0.2, ["failed"])
    learning_a.add_lesson("lesson-a", task_a, "A private lesson")
    learning_b.add_lesson("lesson-b", task_b, "B private lesson")
    learning_a.add_proposal("proposal-a", task_a, "A issue", "A change")
    learning_b.add_proposal("proposal-b", task_b, "B issue", "B change")

    assert [x["evaluation_id"] for x in learning_a.list_evaluations(task_a)] == ["eval-a"]
    assert [x["lesson_id"] for x in learning_a.list_lessons(task_a)] == ["lesson-a"]
    assert [x["proposal_id"] for x in learning_a.list_proposals(task_a)] == ["proposal-a"]
    assert [x["evaluation_id"] for x in learning_b.list_evaluations(task_b)] == ["eval-b"]


@pytest.mark.parametrize("operation", ["evaluation", "lesson", "proposal"])
def test_cross_tenant_parent_cannot_receive_child_learning_record(db, operation):
    tasks_a = TenantTaskRepository(db, principal("a"))
    tasks_b = TenantTaskRepository(db, principal("b"))
    task_b = tasks_b.create_task("B protected")
    learning_a = TenantLearningRepository(db, principal("a"))

    with pytest.raises(TenantTaskNotFound):
        if operation == "evaluation":
            learning_a.add_evaluation("x", task_b, True, 1.0, [])
        elif operation == "lesson":
            learning_a.add_lesson("x", task_b, "forged lesson")
        else:
            learning_a.add_proposal("x", task_b, "forged", "forged")


def test_learning_reads_require_specific_scopes(db):
    task_repo = TenantTaskRepository(db, principal("a"))
    task_id = task_repo.create_task("Task")
    reader = TenantLearningRepository(db, principal("a", {"tasks:read"}))
    with pytest.raises(AuthorizationDenied):
        reader.list_lessons(task_id)
    with pytest.raises(AuthorizationDenied):
        reader.add_lesson("lesson", task_id, "No scope")


def test_database_composite_foreign_keys_reject_cross_tenant_learning_rows(db):
    task_repo = TenantTaskRepository(db, principal("a"))
    task_id = task_repo.create_task("A task")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """INSERT INTO tenant_lessons
               (lesson_id, tenant_id, task_id, summary, validated)
               VALUES ('bad', 'b', ?, 'invalid', 0)""",
            (task_id,),
        )


def test_deleting_task_cascades_to_all_learning_records(db):
    tasks = TenantTaskRepository(db, principal("a"))
    learning = TenantLearningRepository(db, principal("a"))
    task_id = tasks.create_task("Task to remove")
    learning.add_evaluation("eval", task_id, True, 1.0, [])
    learning.add_lesson("lesson", task_id, "Lesson")
    learning.add_proposal("proposal", task_id, "Problem", "Change")

    tasks.delete_task(task_id)
    for table in ("tenant_evaluations", "tenant_lessons", "tenant_proposals"):
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
