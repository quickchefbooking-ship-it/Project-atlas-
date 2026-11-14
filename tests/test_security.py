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
        ("/professor/learning", "GET"),
        ("/professor/voice", "GET"),
        ("/professor/evidence-review", "GET"),
        ("/professor/report", "GET"),
    }
    verified_identity_routes = {
        ("/identity/me", "GET"),
        ("/professor/tenant/plans/{plan_id}", "GET"),
        ("/professor/tenant/plans", "POST"),
        ("/professor/tenant/plans/{plan_id}/prepare", "POST"),
        ("/professor/tenant/plans/{plan_id}/execute-next", "POST"),
        ("/professor/tenant/plans/{plan_id}/evidence/{bundle_step_id}/review", "POST"),
        ("/professor/tenant/plans/{plan_id}/evidence/{bundle_step_id}/review", "GET"),
    }
    unprotected = []
    for route in app_module.app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or set():
            if (route.path, method) in intentionally_public:
                continue
            if (route.path, method) in verified_identity_routes:
                protected = any(
                    dependency.call is app_module.require_verified_principal
                    for dependency in route.dependant.dependencies
                )
            else:
                protected = any(
                    dependency.call is app_module.require_api_key
                    for dependency in route.dependant.dependencies
                )
            if not protected:
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


def test_development_entrypoint_binds_loopback_when_authentication_is_disabled(monkeypatch):
    import uvicorn

    captured = {}
    monkeypatch.setattr(app_module, "API_REQUIRE_AUTH", False)
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: captured.update(kwargs))

    app_module.run_server()

    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8000
    assert captured["reload"] is False


def test_development_entrypoint_preserves_network_binding_when_authentication_is_enabled(monkeypatch):
    import uvicorn

    captured = {}
    monkeypatch.setattr(app_module, "API_REQUIRE_AUTH", True)
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: captured.update(kwargs))

    app_module.run_server()

    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 8000
    assert captured["reload"] is False


def test_proposal_review_is_disabled_even_with_shared_api_key_until_verified_identity_exists(monkeypatch):
    monkeypatch.setattr(app_module, "API_REQUIRE_AUTH", True)
    monkeypatch.setattr(app_module, "API_KEY", "test-secret")
    monkeypatch.delenv("ATLAS_API_KEY", raising=False)
    client = TestClient(app_module.app)

    response = client.post(
        "/proposals/proposal-example/review",
        headers={"X-API-Key": "test-secret"},
        json={"action": "approve", "approved_by": "forged-admin"},
    )

    assert response.status_code == 503
    assert "verified human identity" in response.json()["detail"]



def test_identity_introspection_does_not_accept_shared_api_key_as_human_identity(monkeypatch):
    monkeypatch.setattr(app_module, "API_REQUIRE_AUTH", True)
    monkeypatch.setattr(app_module, "API_KEY", "test-secret")
    monkeypatch.delenv("ATLAS_API_KEY", raising=False)
    client = TestClient(app_module.app)

    response = client.get("/identity/me", headers={"X-API-Key": "test-secret"})

    assert response.status_code == 503
    assert "Verified user identity is not configured" in response.json()["detail"]
