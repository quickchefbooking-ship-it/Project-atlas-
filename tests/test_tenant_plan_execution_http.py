import sqlite3
import time

from fastapi.testclient import TestClient

import app as app_module
from atlas_engine.http_identity import VerifiedIdentityService
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.oidc_contract import OIDCProviderConfig, VerifiedTokenClaims
from atlas_engine.plan_contract import PlanState, PlanStep, ProfessorPlan, RiskClass
from atlas_engine.tenant_membership import SQLiteMembershipRegistry
from atlas_engine.tenant_plan_repository import TenantPlanRepository

ISSUER = "https://identity.execution.test/"
CONFIG = OIDCProviderConfig(
    issuer=ISSUER, audience="atlas-api",
    jwks_uri=ISSUER + ".well-known/jwks.json",
    allowed_algorithms=frozenset({"RS256"}),
)


class SubjectVerifier:
    def __init__(self):
        self.subject = "operator"

    def verify(self, _token):
        now = int(time.time())
        return VerifiedTokenClaims(
            issuer=ISSUER, subject=self.subject, audiences=("atlas-api",),
            expires_at=now + 300, not_before=now - 10, roles=(),
        )


def setup(monkeypatch, tmp_path):
    from atlas_engine import storage
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "core.sqlite"))
    storage.init_db()
    tenant_path = str(tmp_path / "tenant.sqlite")
    membership_path = str(tmp_path / "members.sqlite")
    monkeypatch.setenv("ATLAS_TENANT_DATA_DB_PATH", tenant_path)
    monkeypatch.setenv("ATLAS_MEMBERSHIP_DB_PATH", membership_path)
    for name in ("ATLAS_OIDC_ISSUER", "ATLAS_OIDC_AUDIENCE",
                 "ATLAS_OIDC_JWKS_URI", "ATLAS_OIDC_ALLOWED_ALGORITHMS"):
        monkeypatch.delenv(name, raising=False)
    memberships = SQLiteMembershipRegistry(membership_path)
    memberships.initialize()
    memberships.create_tenant("tenant-a", "Tenant A")
    scopes = {
        "plans:read", "plans:write", "plans:execute",
        "steps:read", "steps:claim", "steps:heartbeat", "steps:complete",
        "compute:local",
    }
    memberships.provision_membership(ISSUER, "operator", "tenant-a", scopes)
    client_context = TestClient(app_module.app)
    client_context.__enter__()
    verifier = SubjectVerifier()
    app_module.app.state.identity_service = VerifiedIdentityService(CONFIG, verifier, memberships)
    app_module.app.state.tenant_capability_runtime = app_module.build_default_capability_runtime()
    app_module.app.state.tenant_capability_registry = app_module.app.state.tenant_capability_runtime.registry
    connection = sqlite3.connect(tenant_path)
    connection.row_factory = sqlite3.Row
    principal = RequestPrincipal(ISSUER, "operator", "tenant-a", True, frozenset(scopes))
    plans = TenantPlanRepository(connection, principal)
    plan = ProfessorPlan(
        "math-plan", "Calculate two arithmetic steps", ("Both results are recorded",),
        (
            PlanStep("first", "math.calculate", "2 + 2", RiskClass.LOCAL_COMPUTATION,
                     required_scopes=("compute:local",), capability_version="1.0.0"),
            PlanStep("second", "math.calculate", "6 * 7", RiskClass.LOCAL_COMPUTATION,
                     depends_on=("first",), required_scopes=("compute:local",), capability_version="1.0.0"),
        ),
    )
    plans.create(plan)
    connection.close()
    headers = {"Authorization": "Bearer valid-test-token"}
    prepared = client_context.post("/professor/tenant/plans/math-plan/prepare", headers=headers)
    assert prepared.status_code == 200 and prepared.json()["state"] == "ready"
    return client_context, verifier, headers


def test_execute_next_runs_one_bounded_step_then_completes_plan(monkeypatch, tmp_path):
    client, _verifier, headers = setup(monkeypatch, tmp_path)
    try:
        first = client.post("/professor/tenant/plans/math-plan/execute-next", headers=headers)
        assert first.status_code == 200
        assert first.json()["status"] == "step_succeeded"
        assert first.json()["result"] == {"value": 4, "kind": "number"}
        assert first.json()["plan_state"] == "running"

        second = client.post("/professor/tenant/plans/math-plan/execute-next", headers=headers)
        assert second.status_code == 200
        assert second.json()["status"] == "completed"
        assert second.json()["result"] == {"value": 42, "kind": "number"}
        assert second.json()["plan_state"] == "succeeded"
    finally:
        client.__exit__(None, None, None)


def test_execute_next_rejects_missing_execution_scope(monkeypatch, tmp_path):
    client, verifier, headers = setup(monkeypatch, tmp_path)
    try:
        verifier.subject = "viewer"
        response = client.post("/professor/tenant/plans/math-plan/execute-next", headers=headers)
        assert response.status_code == 403
    finally:
        client.__exit__(None, None, None)


def test_execute_next_does_not_run_external_or_privileged_capabilities(monkeypatch, tmp_path):
    client, _verifier, headers = setup(monkeypatch, tmp_path)
    try:
        # The trusted runtime has no external or privileged handlers. The route
        # can only execute plans which passed the central readiness preview.
        response = client.post("/professor/tenant/plans/math-plan/execute-next", headers=headers)
        assert response.status_code == 200
        assert response.json()["result"]["value"] == 4
    finally:
        client.__exit__(None, None, None)
