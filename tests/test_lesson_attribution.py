import json

import pytest

from atlas_engine import storage
from atlas_engine.evaluator import Evaluator
from atlas_engine.lesson_contract import LessonAwareResult
from atlas_engine.task_manager import TaskAPI, TaskManager


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "lesson-attribution.db"))
    storage.init_db()
    manager = TaskManager(storage)
    task = manager.create_task(
        "Lesson-aware task",
        "Use the reviewed lesson to calculate the answer",
        [{"field": "value", "operator": "==", "expected_value": 42}],
    )
    now = storage.now_isoformat()
    storage.save_lesson({
        "id": "lesson-reviewed",
        "task_id": task.id,
        "lesson_type": "reviewed",
        "summary": "A validated lesson supplied to the executor.",
        "source": "test-review",
        "evidence_json": "{}",
        "validated": True,
        "created_at": now,
    })
    return manager, task


def _events(task_id):
    conn = storage.get_connection()
    try:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM lesson_usage_events WHERE task_id = ?",
            (task_id,),
        ).fetchall()]
    finally:
        conn.close()


def test_lesson_receipt_is_persisted_with_successful_task_outcome(tmp_path, monkeypatch):
    manager, task = _setup(tmp_path, monkeypatch)

    class Memory:
        @staticmethod
        def get_relevant_lessons(_description):
            return [{"id": "lesson-reviewed", "validated": True}]

    class Executor:
        @staticmethod
        def execute(_payload):
            return LessonAwareResult(
                output={"value": 42},
                consumed_lesson_ids=("lesson-reviewed",),
            )

    api = TaskAPI(manager, Executor(), Evaluator(), Memory(), None, None)
    response = api.run_task(task.id)

    assert response["status"] == "passed"
    assert response["result"] == {"value": 42}
    events = _events(task.id)
    assert len(events) == 1
    assert events[0]["lesson_id"] == "lesson-reviewed"
    assert events[0]["task_id"] == task.id
    attempts = storage.get_task_attempts(task.id)
    assert events[0]["attempt_id"] == attempts[0]["attempt_id"]
    assert len(storage.get_evaluations_for_task(task.id)) == 1


def test_unvalidated_receipt_fails_closed_and_is_not_attributed(tmp_path, monkeypatch):
    manager, task = _setup(tmp_path, monkeypatch)

    class Memory:
        @staticmethod
        def get_relevant_lessons(_description):
            return [{"id": "lesson-reviewed", "validated": False}]

    class Executor:
        @staticmethod
        def execute(_payload):
            return LessonAwareResult(
                output={"value": 42},
                consumed_lesson_ids=("lesson-reviewed",),
            )

    api = TaskAPI(manager, Executor(), Evaluator(), Memory(), None, None)
    response = api.run_task(task.id)

    assert response["status"] == "failed"
    assert _events(task.id) == []
    assert len(storage.get_evaluations_for_task(task.id)) == 1


def test_invalid_lesson_attribution_rolls_back_task_evaluation_and_lease(tmp_path, monkeypatch):
    manager, task = _setup(tmp_path, monkeypatch)
    attempt = storage.claim_task_with_lease(task.id, "worker-test", 30)
    assert attempt is not None
    record = {
        "id": "evaluation-atomic-test",
        "task_id": task.id,
        "passed": True,
        "score": 1.0,
        "reasons_json": "[]",
        "missing_requirements_json": "[]",
        "method": "deterministic",
        "created_at": storage.now_isoformat(),
    }

    with pytest.raises(ValueError, match="unknown or unvalidated"):
        storage.complete_task_with_evaluation(
            task.id,
            record,
            "passed",
            {"value": 42},
            attempt=attempt,
            consumed_lesson_ids=("lesson-does-not-exist",),
        )

    assert manager.get_task(task.id).status == "running"
    assert storage.get_task_attempts(task.id)[0]["state"] == "active"
    assert storage.get_evaluations_for_task(task.id) == []
    assert _events(task.id) == []


def test_legacy_executor_without_receipt_keeps_existing_behavior(tmp_path, monkeypatch):
    manager, task = _setup(tmp_path, monkeypatch)

    class Memory:
        @staticmethod
        def get_relevant_lessons(_description):
            return [{"id": "lesson-reviewed", "validated": True}]

    class Executor:
        @staticmethod
        def execute(_payload):
            return {"value": 42}

    api = TaskAPI(manager, Executor(), Evaluator(), Memory(), None, None)
    response = api.run_task(task.id)

    assert response["status"] == "passed"
    assert _events(task.id) == []
