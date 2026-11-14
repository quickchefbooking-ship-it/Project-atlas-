import sqlite3
import time

from fastapi.testclient import TestClient

import app as app_module
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.oidc_contract import OIDCProviderConfig, VerifiedTokenClaims
from atlas_engine.http_identity import VerifiedIdentityService
from atlas_engine.tenant_membership import SQLiteMembershipRegistry
from atlas_engine.tenant_plan_repository import TenantPlanRepository
from atlas_engine.tenant_step_execution_repository import TenantStepExecutionRepository
from atlas_engine.plan_contract import PlanState, PlanStep, ProfessorPlan, RiskClass


ISSUER = "https://identity.example.test/"
CONFIG = OIDCProviderConfig(
    issuer=ISSUER,
    audience="atlas-api",
    jwks_uri=ISSUER + ".well-known/jwks.json",
    allowed_algorithms=frozenset({"RS256"}),
)


class SubjectVerifier:
    def __init__(self):
        self.subject = "alice"

    def verify(self, _token):
        now = int(time.time())
        return VerifiedTokenClaims(
            issuer=ISSUER,
            subject=self.subject,
            audiences=("atlas-api",),
            expires_at=now + 300,
            not_before=now - 10,
            roles=(),
        )


def test_tenant_plan_inspection_is_bearer_authenticated_and_tenant_scoped(monkeypatch, tmp_path):
    from atlas_engine import storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "core.sqlite"))
    monkeypatch.setenv("ATLAS_TENANT_DATA_DB_PATH", str(tmp_path / "tenant-plans.sqlite"))
    monkeypatch.setenv("ATLAS_MEMBERSHIP_DB_PATH", str(tmp_path / "memberships.sqlite"))
    for name in ("ATLAS_OIDC_ISSUER", "ATLAS_OIDC_AUDIENCE",
                 "ATLAS_OIDC_JWKS_URI", "ATLAS_OIDC_ALLOWED_ALGORITHMS"):
        monkeypatch.delenv(name, raising=False)

    memberships = SQLiteMembershipRegistry(str(tmp_path / "memberships.sqlite"))
    memberships.initialize()
    memberships.create_tenant("tenant-a", "Tenant A")
    memberships.create_tenant("tenant-b", "Tenant B")
    memberships.provision_membership(
        ISSUER, "alice", "tenant-a", {"plans:read", "steps:read"}
    )
    memberships.provision_membership(
        ISSUER, "bob", "tenant-b", {"plans:read", "steps:read"}
    )
    memberships.provision_membership(
        ISSUER, "reader", "tenant-a", {"steps:read"}
    )

    with TestClient(app_module.app) as client:
        verifier = SubjectVerifier()
        app_module.app.state.identity_service = VerifiedIdentityService(
            CONFIG, verifier, memberships
        )

        connection = sqlite3.connect(str(tmp_path / "tenant-plans.sqlite"))
        connection.row_factory = sqlite3.Row
        alice = RequestPrincipal(
            ISSUER, "alice", "tenant-a", True,
            frozenset({"plans:read", "steps:read", "plans:write"}),
        )
        plans = TenantPlanRepository(connection, alice)
        TenantStepExecutionRepository(connection, alice)
        plan = ProfessorPlan(
            "plan-a", "Research a question", ("Evidence is recorded",),
            (PlanStep("research", "knowledge.search", "Find evidence", RiskClass.READ_ONLY),),
        )
        plans.create(plan)
        plans.transition(
            "plan-a", expected_state=PlanState.DRAFT, new_state=PlanState.READY
        )
        connection.close()

        response = client.get(
            "/professor/tenant/plans/plan-a",
            headers={"Authorization": "Bearer valid-test-token"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["tenant_id"] == "tenant-a"
        assert body["plan"]["plan_id"] == "plan-a"
        assert body["readiness"]["steps"][0]["readiness"] == "blocked_missing_capability"
        assert body["execution_enabled"] is False

        # A valid user from another tenant cannot infer this plan exists.
        verifier.subject = "bob"
        cross_tenant = client.get(
            "/professor/tenant/plans/plan-a",
            headers={"Authorization": "Bearer valid-test-token"},
        )
        assert cross_tenant.status_code == 404

        # A tenant member without plans:read cannot inspect the plan.
        verifier.subject = "reader"
        insufficient_scope = client.get(
            "/professor/tenant/plans/plan-a",
            headers={"Authorization": "Bearer valid-test-token"},
        )
        assert insufficient_scope.status_code == 403

        # A shared API key is not a substitute for a verified human identity.
        api_key_only = client.get(
            "/professor/tenant/plans/plan-a",
            headers={"X-API-Key": "not-a-human-session"},
        )
        assert api_key_only.status_code == 401
