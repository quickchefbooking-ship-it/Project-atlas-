import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from atlas_engine.capability_registry import CapabilityDefinition, CapabilityRegistry
from atlas_engine.http_identity import require_verified_principal
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.plan_contract import PlanStep, ProfessorPlan, RiskClass
from atlas_engine.tenant_plan_lifecycle import router
from atlas_engine.tenant_plan_repository import TenantPlanRepository, initialize_tenant_plan_schema


def make_preview_client(tmp_path, scopes=frozenset({"plans:read", "plans:write", "public.research.read"})):
    path = tmp_path / "plans.sqlite"
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    initialize_tenant_plan_schema(db)
    principal = RequestPrincipal("https://issuer.example", "subject-a", "tenant-a", True, scopes)
    plan = ProfessorPlan(
        "plan-a", "Research a topic", ("Return sourced findings",),
        (PlanStep("lookup", "research.lookup", "Find sources", RiskClass.READ_ONLY,
                  required_scopes=("public.research.read",), capability_version="1"),),
    )
    if "plans:write" in scopes:
        TenantPlanRepository(db, principal).create(plan)
    db.close()

    registry = CapabilityRegistry([CapabilityDefinition(
        name="research.lookup", version="1", risk_class="read_only",
        input_schema={"type":"object","properties":{"query":{"type":"string"}},"required":["query"],"additionalProperties":False},
        output_schema={"type":"object","properties":{"title":{"type":"string"}},"required":["title"],"additionalProperties":False},
        required_scopes=("public.research.read",), timeout_seconds=8,
    )])
    app = FastAPI()
    app.state.tenant_data_path = str(path)
    app.state.tenant_capability_registry = registry
    app.dependency_overrides[require_verified_principal] = lambda: principal
    app.include_router(router)
    return TestClient(app), path


def test_preview_is_non_mutating_and_reports_readiness(tmp_path):
    client, path = make_preview_client(tmp_path)
    response = client.get("/professor/tenant/plans/plan-a/preview")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "preview_ready"
    assert body["mutated"] is False
    assert body["execution_enabled"] is False
    assert body["readiness"]["ordered_step_ids"] == ["lookup"]
    db = sqlite3.connect(path)
    assert db.execute("SELECT state FROM tenant_professor_plans WHERE plan_id='plan-a'").fetchone()[0] == "draft"
    db.close()


def test_preview_rejects_missing_plan_read_scope(tmp_path):
    client, _path = make_preview_client(tmp_path, frozenset({"plans:write", "public.research.read"}))
    response = client.get("/professor/tenant/plans/plan-a/preview")
    assert response.status_code == 403
