import pytest
from fastapi.testclient import TestClient

from app import app
from atlas_engine.evaluator import Evaluator
from atlas_engine.executor import safe_execute_local


def test_health_endpoint():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_safe_local_arithmetic():
    result = safe_execute_local({"title": "sum", "description": "14 + 8"})
    assert result == {"type": "safe_math", "value": 22}


def test_executor_rejects_unsupported_code():
    try:
        safe_execute_local({"title": "unsafe", "description": "__import__('os').system('whoami')"})
    except ValueError:
        return
    raise AssertionError("Unsupported expressions must be rejected")



@pytest.mark.parametrize("expression", [
    "1000000000000001",
    "1e309",
    "(-1) ** 0.5",
])
def test_executor_rejects_out_of_range_non_finite_and_complex_results(expression):
    with pytest.raises(ValueError):
        safe_execute_local({"description": expression})


def test_executor_rejects_oversized_arithmetic_expression():
    with pytest.raises(ValueError, match="maximum permitted length"):
        safe_execute_local({"description": "1" + " " * 256 + "+ 1"})


def test_evaluator_passes_matching_criteria():
    result = Evaluator.evaluate(
        {"value": 22},
        [{"field": "value", "operator": "==", "expected_value": 22}],
    )
    assert result["passed"] is True
    assert result["score"] == 1.0


def test_evaluator_fails_non_matching_criteria():
    result = Evaluator.evaluate(
        {"value": 22},
        [{"field": "value", "operator": "==", "expected_value": 99}],
    )
    assert result["passed"] is False
    assert result["score"] == 0.0



def test_task_run_persists_evaluation_and_increments_attempts(tmp_path, monkeypatch):
    from atlas_engine import storage
    from atlas_engine.task_manager import TaskAPI, TaskManager

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "test-atlas.db"))
    storage.init_db()
    manager = TaskManager(storage)
    task = manager.create_task(
        "Check arithmetic",
        "Return the computed value",
        [{"field": "value", "operator": "==", "expected_value": 2}],
    )

    class Executor:
        @staticmethod
        def execute(_payload):
            return {"value": 2}

    class Memory:
        @staticmethod
        def save_lesson_for_task(*_args, **_kwargs):
            raise AssertionError("A passing task should not create a failure lesson")

    class Improvement:
        @staticmethod
        def list_proposals():
            return []

    api = TaskAPI(manager, Executor(), Evaluator(), Memory(), Improvement(), None)
    result = api.run_task(task.id)

    assert result["status"] == "passed"
    updated = manager.get_task(task.id)
    assert updated.attempts == 1
    evaluations = storage.get_evaluations_for_task(task.id)
    assert len(evaluations) == 1
    assert evaluations[0]["passed"] == 1
    assert evaluations[0]["score"] == 1.0


def test_private_api_routes_require_api_key(monkeypatch):
    import app as service

    monkeypatch.setattr(service, "API_REQUIRE_AUTH", True)
    monkeypatch.setattr(service, "API_KEY", "test-only-secret")
    monkeypatch.delenv("ATLAS_API_KEY", raising=False)
    client = TestClient(service.app)

    assert client.get("/health").status_code == 200
    assert client.get("/tasks").status_code == 401
    assert client.get("/tasks", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/tasks", headers={"X-API-Key": "test-only-secret"}).status_code == 200


def test_private_api_fails_closed_when_key_missing(monkeypatch):
    import app as service

    monkeypatch.setattr(service, "API_REQUIRE_AUTH", True)
    monkeypatch.setattr(service, "API_KEY", None)
    monkeypatch.delenv("ATLAS_API_KEY", raising=False)
    response = TestClient(service.app).get("/dashboard")
    assert response.status_code == 503

def test_evaluator_treats_missing_or_incompatible_ordered_values_as_failed_criteria():
    result = Evaluator.evaluate(
        {},
        [{"field": "count", "operator": "gt", "expected_value": 3}],
    )

    assert result["passed"] is False
    assert result["score"] == 0.0
    assert result["reasons"] == ["field is missing"]
    assert result["missing_requirements"] == ["count gt 3"]


def test_evaluator_does_not_pass_not_equal_when_result_field_is_missing():
    criteria = [{"field": "status", "operator": "!=", "expected_value": "complete"}]

    missing = Evaluator.evaluate({}, criteria)
    present = Evaluator.evaluate({"status": "pending"}, criteria)

    assert missing["passed"] is False
    assert missing["score"] == 0.0
    assert missing["reasons"] == ["field is missing"]
    assert missing["missing_requirements"] == ["status != complete"]
    assert present["passed"] is True
    assert present["score"] == 1.0


def test_task_failure_does_not_expose_exception_details(tmp_path, monkeypatch, caplog):
    from atlas_engine import storage
    from atlas_engine.task_manager import TaskAPI, TaskManager

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "failure-test.db"))
    storage.init_db()
    manager = TaskManager(storage)
    task = manager.create_task("Fail safely", "Trigger a controlled failure", [])

    class BrokenExecutor:
        @staticmethod
        def execute(_payload):
            raise RuntimeError("private-token-and-path-must-not-leak")

    class Memory:
        @staticmethod
        def save_lesson_for_task(*_args, **_kwargs):
            return None

    api = TaskAPI(manager, BrokenExecutor(), Evaluator(), Memory(), None, None)
    result = api.run_task(task.id)

    assert result["status"] == "failed"
    assert result["error"] == "Task execution failed. Check the server diagnostics using the task ID."
    assert "private-token-and-path-must-not-leak" not in str(result)
    assert "RuntimeError" in caplog.text
    assert "private-token-and-path-must-not-leak" not in caplog.text
    assert manager.get_task(task.id).status == "failed"
    evaluations = storage.get_evaluations_for_task(task.id)
    assert len(evaluations) == 1
    assert evaluations[0]["passed"] == 0
    assert evaluations[0]["method"] == "execution_error"
    assert "RuntimeError" in evaluations[0]["reasons_json"]
    assert "private-token-and-path-must-not-leak" not in evaluations[0]["reasons_json"]


def test_storage_enforces_foreign_key_relationships(tmp_path, monkeypatch):
    import json
    import sqlite3
    from datetime import datetime, timezone
    from atlas_engine import storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "foreign-keys.db"))
    storage.init_db()
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "id": "evaluation-without-task",
        "task_id": "task-does-not-exist",
        "passed": False,
        "score": 0.0,
        "reasons_json": json.dumps(["missing task"]),
        "missing_requirements_json": json.dumps([]),
        "method": "test",
        "created_at": now,
    }

    try:
        storage.save_evaluation(record)
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("An evaluation must not reference a task that does not exist")


def test_learning_memory_generates_unique_ids_for_rapid_lessons(tmp_path, monkeypatch):
    from atlas_engine import storage
    from atlas_engine.learning_memory import LearningMemory
    from atlas_engine.task_manager import TaskManager

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "lesson-ids.db"))
    storage.init_db()
    manager = TaskManager(storage)
    task = manager.create_task("Memory identity", "Check unique lesson identifiers", [])

    first = LearningMemory.save_lesson_for_task(
        task.id, "observation", "First observation", "test", {"step": 1}
    )
    second = LearningMemory.save_lesson_for_task(
        task.id, "observation", "Second observation", "test", {"step": 2}
    )

    assert first["id"] != second["id"]
    saved = storage.list_lessons(limit=10)
    assert {row["id"] for row in saved} >= {first["id"], second["id"]}


def test_validated_memory_is_not_hidden_by_newer_unvalidated_lessons(tmp_path, monkeypatch):
    from atlas_engine import storage
    from atlas_engine.learning_memory import LearningMemory
    from atlas_engine.task_manager import TaskManager

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "validated-memory.db"))
    storage.init_db()
    manager = TaskManager(storage)
    task = manager.create_task("Memory retrieval", "Test trusted memory ranking", [])

    # Seed a previously reviewed record at the storage layer. New lesson creation
    # must never self-certify; that invariant is covered in test_learning_memory.py.
    import json
    trusted_id = "lesson-reviewed-fixture"
    storage.save_lesson({
        "id": trusted_id,
        "task_id": task.id,
        "lesson_type": "validated",
        "summary": "precision memory retrieval",
        "source": "reviewed",
        "evidence_json": json.dumps({"trusted": True}, sort_keys=True),
        "validated": True,
        "created_at": storage.now_isoformat(),
    })
    for index in range(105):
        LearningMemory.save_lesson_for_task(
            task.id, "unverified", f"unverified unrelated note {index}", "observation", {"trusted": False}
        )

    relevant = LearningMemory.get_relevant_lessons("precision memory retrieval", limit=5)

    assert trusted_id in {lesson["id"] for lesson in relevant}
    assert all(lesson["validated"] in (1, True) for lesson in relevant)


def test_task_execution_receives_relevant_validated_memory(tmp_path, monkeypatch):
    from atlas_engine import storage
    from atlas_engine.task_manager import TaskAPI, TaskManager

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "memory-context.db"))
    storage.init_db()
    manager = TaskManager(storage)
    task = manager.create_task(
        "Use prior knowledge",
        "Apply the validated lesson about arithmetic",
        [{"field": "value", "operator": "==", "expected_value": 5}],
    )
    trusted_lesson = {"id": "lesson-trusted", "summary": "Prior arithmetic lesson", "validated": 1}
    from atlas_engine.source_division import ingest_document, register_source, review_document
    register_source("test-research", "Test Research", "test")
    source_doc = ingest_document(
        "test-research", "Arithmetic reference", "https://example.org/arithmetic",
        "Validated reference for applying arithmetic operations.",
    )
    review_document(source_doc["id"], "approved", "test-reviewer")

    class Memory:
        @staticmethod
        def get_relevant_lessons(_description):
            return [trusted_lesson]

        @staticmethod
        def save_lesson_for_task(*_args, **_kwargs):
            return None

    class ContextAwareExecutor:
        def __init__(self):
            self.payload = None

        def execute(self, payload):
            self.payload = payload
            return {"value": 5}

    executor = ContextAwareExecutor()
    api = TaskAPI(manager, executor, Evaluator(), Memory(), None, None)

    result = api.run_task(task.id)

    assert result["status"] == "passed"
    assert executor.payload["relevant_lessons"] == [trusted_lesson]
    assert len(executor.payload["source_documents"]) == 1
    assert executor.payload["source_documents"][0]["uri"] == "https://example.org/arithmetic"

def test_evaluator_rejects_subjective_criteria_until_a_subjective_evaluator_exists():
    result = Evaluator.evaluate(
        {"summary": "Looks good"},
        [{
            "field": "summary",
            "operator": "contains",
            "expected_value": "good",
            "deterministic": False,
            "description": "Human-quality review",
        }],
    )

    assert result["passed"] is False
    assert result["score"] == 0.0
    assert result["method"] == "deterministic"
    assert "Subjective criteria require an evaluator" in result["reasons"][0]
    assert result["missing_requirements"] == ["Human-quality review"]


def test_evaluator_handles_non_string_contains_expected_value():
    result = Evaluator.evaluate(
        {"summary": "A valid summary"},
        [{"field": "summary", "operator": "contains", "expected_value": 42}],
    )

    assert result["passed"] is False
    assert result["score"] == 0.0
    assert result["reasons"] == ["expected value is not a string"]



def test_task_claim_is_atomic_and_increments_attempt_once(tmp_path, monkeypatch):
    from atlas_engine import storage
    from atlas_engine.task_manager import TaskManager

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "atomic-task-claim.db"))
    storage.init_db()
    manager = TaskManager(storage)
    task = manager.create_task("Atomic claim", "Ensure one worker owns this task", [])

    from concurrent.futures import ThreadPoolExecutor

    # Race several independent callers against the same pending task.
    with ThreadPoolExecutor(max_workers=8) as workers:
        claims = list(workers.map(lambda _index: manager.claim_task(task.id), range(8)))

    assert claims.count(True) == 1
    assert claims.count(False) == 7

    persisted = manager.get_task(task.id)
    assert persisted.status == "running"
    assert persisted.attempts == 1



def test_task_completion_and_evaluation_are_atomic(tmp_path, monkeypatch):
    import pytest
    from atlas_engine import storage
    from atlas_engine.task_manager import TaskManager

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "atomic-completion.db"))
    storage.init_db()
    manager = TaskManager(storage)
    task = manager.create_task("Atomic completion", "Persist outcome and evaluation together", [])
    assert manager.claim_task(task.id) is True

    # The missing method field fails after the task UPDATE has executed. The
    # transaction must roll that state change back as well.
    incomplete_record = {
        "id": "evaluation-incomplete",
        "task_id": task.id,
        "passed": True,
        "score": 1.0,
        "reasons_json": "[]",
        "missing_requirements_json": "[]",
        "created_at": storage.now_isoformat(),
    }
    with pytest.raises(KeyError):
        storage.complete_task_with_evaluation(
            task.id, incomplete_record, "passed", {"value": 2}
        )

    persisted = manager.get_task(task.id)
    assert persisted.status == "running"
    assert persisted.score == 0.0
    assert persisted.result is None
    assert storage.get_evaluations_for_task(task.id) == []


def test_failed_task_result_survives_failure_to_save_learning_lesson(tmp_path, monkeypatch, caplog):
    from atlas_engine import storage
    from atlas_engine.task_manager import TaskAPI, TaskManager

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "lesson-write-failure.db"))
    storage.init_db()
    manager = TaskManager(storage)
    task = manager.create_task(
        "Failed evaluation",
        "Return a value that does not meet the criterion",
        [{"field": "value", "operator": "==", "expected_value": 99}],
    )

    class Executor:
        @staticmethod
        def execute(_payload):
            return {"value": 2}

    class BrokenMemory:
        @staticmethod
        def save_lesson_for_task(*_args, **_kwargs):
            raise OSError("private storage location")

    api = TaskAPI(manager, Executor(), Evaluator(), BrokenMemory(), None, None)
    result = api.run_task(task.id)

    assert result["status"] == "failed"
    assert result["evaluation"]["passed"] is False
    assert "error" not in result
    persisted = manager.get_task(task.id)
    assert persisted.status == "failed"
    assert persisted.result == {"value": 2}
    assert len(storage.get_evaluations_for_task(task.id)) == 1
    assert "OSError" in caplog.text
    assert "private storage location" not in caplog.text



def test_task_outcome_persistence_failure_does_not_write_unpaired_terminal_status(
    tmp_path, monkeypatch, caplog
):
    from atlas_engine import storage
    from atlas_engine.task_manager import TaskAPI, TaskManager

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "outcome-persistence-failure.db"))
    storage.init_db()
    manager = TaskManager(storage)
    task = manager.create_task(
        "Persistence failure",
        "Do not mark complete without a durable evaluation",
        [{"field": "value", "operator": "==", "expected_value": 7}],
    )

    class Executor:
        @staticmethod
        def execute(_payload):
            return {"value": 7}

    class Memory:
        @staticmethod
        def get_relevant_lessons(_description):
            return []

        @staticmethod
        def save_lesson_for_task(*_args, **_kwargs):
            raise AssertionError("No failure lesson should be saved for a passing evaluation")

    def fail_completion(*_args, **_kwargs):
        raise OSError("private database path must not be logged")

    monkeypatch.setattr(manager, "complete_with_evaluation", fail_completion)
    api = TaskAPI(manager, Executor(), Evaluator(), Memory(), None, None)

    response = api.run_task(task.id)

    assert response["status"] == "outcome_unconfirmed"
    assert "could not be persisted" in response["error"]
    assert "private database path" not in str(response)
    assert "private database path" not in caplog.text
    assert "OSError" in caplog.text
    assert manager.get_task(task.id).status == "running"
    assert storage.get_evaluations_for_task(task.id) == []

def test_task_completion_false_result_never_writes_unpaired_terminal_status(tmp_path, monkeypatch):
    from atlas_engine import storage
    from atlas_engine.task_manager import TaskAPI, TaskManager

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "completion-false-result.db"))
    storage.init_db()
    manager = TaskManager(storage)
    task = manager.create_task(
        "Completion race",
        "A false completion result must not create a terminal status without evaluation",
        [{"field": "value", "operator": "==", "expected_value": 11}],
    )

    class Executor:
        @staticmethod
        def execute(_payload):
            return {"value": 11}

    class Memory:
        @staticmethod
        def get_relevant_lessons(_description):
            return []

        @staticmethod
        def save_lesson_for_task(*_args, **_kwargs):
            raise AssertionError("A passing task must not save a failure lesson")

    monkeypatch.setattr(manager, "complete_with_evaluation", lambda *_args, **_kwargs: False)
    api = TaskAPI(manager, Executor(), Evaluator(), Memory(), None, None)

    response = api.run_task(task.id)

    assert response["status"] == "outcome_unconfirmed"
    assert manager.get_task(task.id).status == "running"
    assert storage.get_evaluations_for_task(task.id) == []


def test_execution_failure_completion_false_result_keeps_task_non_terminal(tmp_path, monkeypatch):
    from atlas_engine import storage
    from atlas_engine.task_manager import TaskAPI, TaskManager

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "failure-completion-false.db"))
    storage.init_db()
    manager = TaskManager(storage)
    task = manager.create_task("Failure completion race", "Preserve paired outcome records", [])

    class BrokenExecutor:
        @staticmethod
        def execute(_payload):
            raise RuntimeError("private detail must not leak")

    class Memory:
        @staticmethod
        def save_lesson_for_task(*_args, **_kwargs):
            return None

    monkeypatch.setattr(manager, "complete_with_evaluation", lambda *_args, **_kwargs: False)
    api = TaskAPI(manager, BrokenExecutor(), Evaluator(), Memory(), None, None)

    response = api.run_task(task.id)

    assert response["status"] == "outcome_unconfirmed"
    assert "private detail" not in str(response)
    assert manager.get_task(task.id).status == "running"
    assert storage.get_evaluations_for_task(task.id) == []

