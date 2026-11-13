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
