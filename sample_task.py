import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import app
from atlas_engine.storage import get_connection, init_db
from atlas_engine.storage import save_task, get_task
from atlas_engine.executor import safe_execute_local
from atlas_engine.evaluator import Evaluator
from atlas_engine.learning_memory import LearningMemory
from atlas_engine.improvement import ImprovementManager


@pytest.fixture
def client():
    init_db()
    with TestClient(app) as test_client:
        yield test_client


def test_create_and_retrieve_task(client):
    payload = {
        "title": "Calculate total",
        "description": "14 + 8",
        "success_criteria": [{"field": "value", "operator": "==", "expected_value": 22.0}],
    }
    response = client.post("/tasks", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Calculate total"
    assert get_task(data["id"]) is not None


def test_sqlite_persistence_across_restart(client):
    payload = {
        "title": "Persisted task",
        "description": "7 * 6",
        "success_criteria": [{"field": "value", "operator": "==", "expected_value": 42.0}],
    }
    response = client.post("/tasks", json=payload)
    assert response.status_code == 200
    task_id = response.json()["id"]

    row = get_task(task_id)
    assert row is not None
    assert row["title"] == "Persisted task"


def test_passing_and_failing_evaluations():
    result = {"value": 22.0}
    passing = Evaluator.evaluate(result, [{"field": "value", "operator": "==", "expected_value": 22.0}])
    failing = Evaluator.evaluate(result, [{"field": "value", "operator": "==", "expected_value": 99.0}])
    assert passing["passed"] is True
    assert failing["passed"] is False
    assert passing["score"] == 1.0
    assert failing["score"] == 0.0


def test_record_lesson_after_failed_task(client):
    task = {
        "title": "Failing task",
        "description": "30 / 4",
        "success_criteria": [{"field": "value", "operator": "==", "expected_value": 99.0}],
    }
    created = client.post("/tasks", json=task)
    task_id = created.json()["id"]
    run = client.post(f"/tasks/{task_id}/run")
    assert run.status_code == 200
    lessons = client.get("/lessons")
    assert lessons.status_code == 200
    assert len(lessons.json()) >= 1


def test_reuse_relevant_validated_lesson():
    task_id = "task-lesson-test"
    lesson = LearningMemory.save_lesson_for_task(
        task_id,
        "mistake",
        "Avoid large arithmetic errors when comparing exact totals.",
        "math-validation",
        {"reason": "exact value mismatch"},
        validated=True,
    )
    relevant = LearningMemory.get_relevant_lessons("Calculate exact total and compare to exact expected value")
    assert len(relevant) >= 1
    assert any(item["summary"] == lesson["summary"] for item in relevant)


def test_create_improvement_proposal_after_failure():
    proposal = ImprovementManager.create_proposal(
        "task-123",
        "The result did not meet the success criteria.",
        {"result": {"value": 9}, "reason": "Mismatch"},
        "Tighten the validation logic and add exact-value checks.",
        "Higher reliability in future tasks.",
        "Run targeted pytest checks in a temporary workspace.",
        created_by="human",
    )
    assert proposal["status"] == "pending"


def test_reject_unauthorised_approval_attempts():
    proposal = ImprovementManager.create_proposal(
        "task-456",
        "Failure needs review.",
        {"reason": "Mismatch"},
        "Improve the task description.",
        "Reduce repeated failure.",
        "Test the revised instructions.",
        created_by="human",
    )
    with pytest.raises(PermissionError):
        ImprovementManager.review_proposal(proposal["id"], "approve", "system")


def test_prevent_unapproved_changes_from_reaching_production():
    proposal = ImprovementManager.create_proposal(
        "task-789",
        "Need approval before production change.",
        {"reason": "Not yet approved"},
        "Refine failure guidance.",
        "Improve task reliability.",
        "Run checks before production change.",
        created_by="human",
    )
    gate = ImprovementManager.check_production_gate(proposal["id"])
    assert gate["allowed"] is False


def test_operates_without_ai_provider_credentials():
    result = safe_execute_local({"title": "math", "description": "5 + 7"})
    assert result["type"] == "safe_math"
    assert round(result["value"], 2) == 12.0


def test_invalid_input_and_execution_errors():
    with pytest.raises(ValueError):
        safe_execute_local({"title": "bad", "description": ""})

    with pytest.raises(ValueError):
        Evaluator.evaluate({"value": 2}, [{"field": "value", "operator": "bad", "expected_value": 2}])


def test_scores_and_success_rates_are_calculated_correctly():
    result_one = Evaluator.evaluate({"value": 10}, [{"field": "value", "operator": "==", "expected_value": 10}])
    result_two = Evaluator.evaluate({"value": 10}, [{"field": "value", "operator": "==", "expected_value": 20}])
    assert result_one["score"] == 1.0
    assert result_two["score"] == 0.0


def test_no_financial_or_external_actions_are_triggered():
    payload = {
        "title": "Money task",
        "description": "Buy BTC automatically",
        "success_criteria": [{"field": "value", "operator": "==", "expected_value": "blocked"}],
    }
    response = client.post("/tasks", json=payload)
    assert response.status_code == 200
    task_id = response.json()["id"]
    run = client.post(f"/tasks/{task_id}/run")
    assert run.status_code == 200
    response_data = run.json()
    assert response_data["evaluation"]["passed"] is False
