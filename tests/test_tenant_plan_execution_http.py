import sqlite3
import time
import json

from fastapi.testclient import TestClient

import app as app_module
from atlas_engine.http_identity import VerifiedIdentityService
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.oidc_contract import OIDCProviderConfig, VerifiedTokenClaims
from atlas_engine.plan_contract import PlanState, PlanStep, ProfessorPlan, RiskClass
from atlas_engine.tenant_membership import SQLiteMembershipRegistry
from atlas_engine.tenant_plan_repository import TenantPlanRepository
from atlas_engine.source_adapters import SourceDocument

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
        "compute:local", "research:public",
    }
    memberships.provision_membership(ISSUER, "operator", "tenant-a", scopes)
    memberships.provision_membership(ISSUER, "viewer", "tenant-a", scopes - {"plans:execute"})
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


def test_execute_next_runs_read_only_crossref_research_and_preserves_citations(monkeypatch, tmp_path):
    client, _verifier, headers = setup(monkeypatch, tmp_path)
    try:
        metadata = {
            "doi": "10.1234/atlas.test",
            "publisher": "Example Academic Press",
            "retrieved_at": "2026-11-14T12:00:00+00:00",
            "abstract": "A public abstract used as untrusted source material.",
        }
        document = SourceDocument(
            title="A study of safe AI orchestration",
            uri="https://doi.org/10.1234/atlas.test",
            content="Crossref scholarly metadata\n" + json.dumps(metadata),
            metadata=metadata,
        )
        calls = []
        def fake_search(query, limit=5):
            calls.append((query, limit))
            return [document]

        monkeypatch.setattr(
            "atlas_engine.capability_runtime.search_crossref_works", fake_search
        )
        from atlas_engine import storage
        tenant_path = str(tmp_path / "tenant.sqlite")
        connection = sqlite3.connect(tenant_path)
        connection.row_factory = sqlite3.Row
        scopes = frozenset({
            "plans:read", "plans:write", "plans:execute",
            "steps:read", "steps:claim", "steps:heartbeat", "steps:complete",
            "compute:local", "research:public",
        })
        principal = RequestPrincipal(ISSUER, "operator", "tenant-a", True, scopes)
        plans = TenantPlanRepository(connection, principal)
        plans.create(ProfessorPlan(
            "research-plan", "Find public scholarly evidence",
            ("Return source-linked scholarly metadata",),
            (PlanStep(
                "search", "research.crossref.search",
                "safe AI orchestration", RiskClass.READ_ONLY,
                required_scopes=("research:public",),
                capability_version="1.0.0",
            ),),
        ))
        connection.close()

        prepared = client.post(
            "/professor/tenant/plans/research-plan/prepare", headers=headers
        )
        assert prepared.status_code == 200
        assert prepared.json()["state"] == "ready"

        response = client.post(
            "/professor/tenant/plans/research-plan/execute-next", headers=headers
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        assert body["plan_state"] == "succeeded"
        assert body["result"]["provider"] == "Crossref"
        assert body["result"]["retrieved_count"] == 1
        assert body["result"]["sources"][0]["uri"] == "https://doi.org/10.1234/atlas.test"
        assert body["result"]["sources"][0]["abstract"] == metadata["abstract"]
        assert "untrusted" in body["result"]["notice"]
        assert calls == [("safe AI orchestration", 3)]
    finally:
        client.__exit__(None, None, None)


def test_professor_hands_crossref_sources_into_evidence_bundle_capability(monkeypatch, tmp_path):
    client, _verifier, headers = setup(monkeypatch, tmp_path)
    try:
        metadata = {
            "doi": "10.1234/atlas.chain",
            "publisher": "Example Academic Press",
            "retrieved_at": "2026-11-14T12:00:00+00:00",
            "abstract": "A bounded source abstract.",
        }
        document = SourceDocument(
            title="Evidence hand-off study",
            uri="https://doi.org/10.1234/atlas.chain",
            content="Crossref scholarly metadata\n" + json.dumps(metadata),
            metadata=metadata,
        )
        monkeypatch.setattr(
            "atlas_engine.capability_runtime.search_crossref_works",
            lambda query, limit=5: [document],
        )
        tenant_path = str(tmp_path / "tenant.sqlite")
        connection = sqlite3.connect(tenant_path)
        connection.row_factory = sqlite3.Row
        scopes = frozenset({
            "plans:read", "plans:write", "plans:execute",
            "steps:read", "steps:claim", "steps:heartbeat", "steps:complete",
            "compute:local", "research:public",
        })
        principal = RequestPrincipal(ISSUER, "operator", "tenant-a", True, scopes)
        plans = TenantPlanRepository(connection, principal)
        plans.create(ProfessorPlan(
            "evidence-chain", "Retrieve and organise scholarly sources",
            ("Keep source provenance throughout the plan",),
            (
                PlanStep(
                    "search", "research.crossref.search", "safe AI orchestration",
                    RiskClass.READ_ONLY, required_scopes=("research:public",),
                    capability_version="1.0.0",
                ),
                PlanStep(
                    "bundle", "research.evidence.bundle", "Organise completed source records",
                    RiskClass.READ_ONLY, depends_on=("search",),
                    required_scopes=("research:public",), capability_version="1.0.0",
                ),
            ),
        ))
        connection.close()

        prepared = client.post(
            "/professor/tenant/plans/evidence-chain/prepare", headers=headers
        )
        assert prepared.status_code == 200
        first = client.post(
            "/professor/tenant/plans/evidence-chain/execute-next", headers=headers
        )
        assert first.status_code == 200
        assert first.json()["status"] == "step_succeeded"
        second = client.post(
            "/professor/tenant/plans/evidence-chain/execute-next", headers=headers
        )
        assert second.status_code == 200
        result = second.json()["result"]
        assert result["schema_version"] == 1
        assert result["summary"]["source_count"] == 1
        assert result["sources"][0]["uri"] == "https://doi.org/10.1234/atlas.chain"
        assert result["summary"]["confidence"] == "not_scored"
    finally:
        client.__exit__(None, None, None)



def test_professor_executes_full_research_evidence_evaluation_report_chain(monkeypatch, tmp_path):
    client, _verifier, headers = setup(monkeypatch, tmp_path)
    try:
        metadata = {
            "doi": "10.1234/atlas.fullchain",
            "publisher": "Example Academic Press",
            "retrieved_at": "2026-11-14T12:00:00+00:00",
            "abstract": "A source abstract retained as untrusted material.",
        }
        document = SourceDocument(
            title="Full Professor workflow study",
            uri="https://doi.org/10.1234/atlas.fullchain",
            content="Crossref scholarly metadata\n" + json.dumps(metadata),
            metadata=metadata,
        )
        calls = []

        def fake_search(query, limit=5):
            calls.append((query, limit))
            return [document]

        monkeypatch.setattr(
            "atlas_engine.capability_runtime.search_crossref_works", fake_search
        )
        tenant_path = str(tmp_path / "tenant.sqlite")
        connection = sqlite3.connect(tenant_path)
        connection.row_factory = sqlite3.Row
        scopes = frozenset({
            "plans:read", "plans:write", "plans:execute",
            "steps:read", "steps:claim", "steps:heartbeat", "steps:complete",
            "compute:local", "research:public",
        })
        principal = RequestPrincipal(ISSUER, "operator", "tenant-a", True, scopes)
        plans = TenantPlanRepository(connection, principal)
        plans.create(ProfessorPlan(
            "professor-full-chain",
            "Research a topic, organise its sources, evaluate annotations and report",
            ("Preserve source provenance and report limitations honestly",),
            (
                PlanStep(
                    "search", "research.crossref.search", "safe AI orchestration",
                    RiskClass.READ_ONLY, required_scopes=("research:public",),
                    capability_version="1.0.0",
                ),
                PlanStep(
                    "bundle", "research.evidence.bundle", "Organise retrieved sources",
                    RiskClass.READ_ONLY, depends_on=("search",),
                    required_scopes=("research:public",), capability_version="1.0.0",
                ),
                PlanStep(
                    "evaluate", "research.evidence.evaluate", "Evaluate supplied annotations",
                    RiskClass.READ_ONLY, depends_on=("bundle",),
                    required_scopes=("research:public",), capability_version="1.0.0",
                ),
                PlanStep(
                    "report", "research.professor.report", "Produce a source-linked report",
                    RiskClass.READ_ONLY, depends_on=("bundle", "evaluate"),
                    required_scopes=("research:public",), capability_version="1.0.0",
                ),
            ),
        ))
        connection.close()

        prepared = client.post(
            "/professor/tenant/plans/professor-full-chain/prepare", headers=headers
        )
        assert prepared.status_code == 200
        assert prepared.json()["state"] == "ready"

        step_results = []
        for _ in range(4):
            response = client.post(
                "/professor/tenant/plans/professor-full-chain/execute-next",
                headers=headers,
            )
            assert response.status_code == 200
            step_results.append(response.json())

        assert [item["step_id"] for item in step_results] == [
            "search", "bundle", "evaluate", "report"
        ]
        assert [item["status"] for item in step_results] == [
            "step_succeeded", "step_succeeded", "step_succeeded", "completed"
        ]
        assert step_results[-1]["plan_state"] == "succeeded"

        report = step_results[-1]["result"]
        assert report["report_type"] == "professor_evidence_report"
        assert report["executive_summary"]["source_count"] == 1
        assert report["executive_summary"]["claim_count"] == 0
        assert report["executive_summary"]["confidence"] == "not_scored"
        assert report["executive_summary"]["overall_conclusion"] == (
            "No overall truth conclusion is drawn from annotation labels alone."
        )
        assert report["findings"] == []
        assert report["challenges"] == []
        assert report["disagreements"] == []
        assert report["evidence_gaps"] == []
        assert report["sources"][0]["uri"] == "https://doi.org/10.1234/atlas.fullchain"
        assert report["sources"][0]["publisher"] == "Example Academic Press"
        assert any("reviewer" in item.lower() or "annotation" in item.lower()
                   for item in report["limitations"])
        assert calls == [("safe AI orchestration", 3)]
    finally:
        client.__exit__(None, None, None)



def test_execute_next_rechecks_capability_scope_after_membership_change(monkeypatch, tmp_path):
    from atlas_engine import capability_runtime

    calls = []
    original_calculate = capability_runtime._calculate

    def tracked_calculate(payload, deadline):
        calls.append(dict(payload))
        return original_calculate(payload, deadline)

    monkeypatch.setattr(capability_runtime, "_calculate", tracked_calculate)
    client, _verifier, headers = setup(monkeypatch, tmp_path)
    try:
        first = client.post(
            "/professor/tenant/plans/math-plan/execute-next", headers=headers
        )
        assert first.status_code == 200
        assert first.json()["status"] == "step_succeeded"
        assert len(calls) == 1

        # Re-provisioning updates the verified membership's scopes. The next
        # HTTP request resolves the new membership rather than trusting the
        # permissions that were present when the plan was prepared.
        memberships = SQLiteMembershipRegistry(str(tmp_path / "members.sqlite"))
        memberships.provision_membership(
            ISSUER,
            "operator",
            "tenant-a",
            {
                "plans:read", "plans:write", "plans:execute",
                "steps:read", "steps:claim", "steps:heartbeat", "steps:complete",
                "research:public",
            },
        )
        second = client.post(
            "/professor/tenant/plans/math-plan/execute-next", headers=headers
        )
        assert second.status_code == 403
        assert "permissions are no longer available" in second.json()["detail"]
        assert len(calls) == 1  # the second handler was never invoked
    finally:
        client.__exit__(None, None, None)
