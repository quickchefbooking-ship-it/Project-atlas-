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
