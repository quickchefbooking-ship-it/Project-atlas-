from fastapi.testclient import TestClient

import app as app_module


def test_private_routes_fail_closed_when_api_key_is_not_configured(monkeypatch):
    monkeypatch.setattr(app_module, "API_REQUIRE_AUTH", True)
    monkeypatch.setattr(app_module, "API_KEY", None)
    monkeypatch.delenv("ATLAS_API_KEY", raising=False)

    response = TestClient(app_module.app).get("/tasks")

    assert response.status_code == 503
    assert TestClient(app_module.app).get("/health").status_code == 200


def test_private_routes_require_the_configured_api_key(monkeypatch):
    monkeypatch.setattr(app_module, "API_REQUIRE_AUTH", True)
    monkeypatch.setattr(app_module, "API_KEY", "test-secret")
    monkeypatch.delenv("ATLAS_API_KEY", raising=False)
    client = TestClient(app_module.app)

    assert client.get("/tasks").status_code == 401
    response = client.get("/tasks", headers={"X-API-Key": "test-secret"})

    assert response.status_code == 200


def test_every_private_api_route_declares_the_api_key_dependency():
    from fastapi.routing import APIRoute

    intentionally_public = {
        ("/health", "GET"),
        ("/media/health", "GET"),
        ("/professor/sources", "GET"),
    }
    unprotected = []
    for route in app_module.app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or set():
            if (route.path, method) in intentionally_public:
                continue
            has_api_key_dependency = any(
                dependency.call is app_module.require_api_key
                for dependency in route.dependant.dependencies
            )
            if not has_api_key_dependency:
                unprotected.append(f"{method} {route.path}")

    assert unprotected == []


def test_task_creation_rejects_unbounded_intake_payloads(monkeypatch, tmp_path):
    from atlas_engine import storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "bounded-task-intake.db"))
    storage.init_db()
    monkeypatch.setattr(app_module, "API_REQUIRE_AUTH", True)
    monkeypatch.setattr(app_module, "API_KEY", "test-secret")
    monkeypatch.delenv("ATLAS_API_KEY", raising=False)
    client = TestClient(app_module.app)
    headers = {"X-API-Key": "test-secret"}

    valid = {
        "title": "Bounded task",
        "description": "A normal task description.",
        "success_criteria": [{"field": "value", "operator": "==", "expected_value": 1}],
    }
    oversized_payloads = [
        {**valid, "title": "t" * 201},
        {**valid, "description": "d" * 10_001},
        {**valid, "success_criteria": [{"field": "value", "operator": "==", "expected_value": i} for i in range(101)]},
        {**valid, "success_criteria": {"field": "value", "operator": "==", "expected_value": "x" * 16_385}},
    ]

    for payload in oversized_payloads:
        response = client.post("/tasks", json=payload, headers=headers)
        assert response.status_code == 422

    assert storage.list_tasks(limit=10) == []


def test_task_creation_rejects_non_finite_success_criteria(monkeypatch, tmp_path):
    from atlas_engine import storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "finite-task-criteria.db"))
    storage.init_db()
    monkeypatch.setattr(app_module, "API_REQUIRE_AUTH", True)
    monkeypatch.setattr(app_module, "API_KEY", "test-secret")
    monkeypatch.delenv("ATLAS_API_KEY", raising=False)
    client = TestClient(app_module.app)

    response = client.post(
        "/tasks",
        headers={"X-API-Key": "test-secret"},
        content='{"title":"Finite task","description":"Reject NaN criteria","success_criteria":{"field":"value","operator":"==","expected_value":NaN}}',
    )

    assert response.status_code == 422
    error_detail = response.json()["detail"][0]
    assert error_detail["type"] == "task_criteria_invalid"
    assert "input" not in error_detail
    assert "ctx" not in error_detail
    assert storage.list_tasks(limit=10) == []
