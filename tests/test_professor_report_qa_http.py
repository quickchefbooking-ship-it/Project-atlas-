import json
import sqlite3
import time

from fastapi.testclient import TestClient

import app as app_module
from atlas_engine.http_identity import VerifiedIdentityService
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.oidc_contract import OIDCProviderConfig, VerifiedTokenClaims
from atlas_engine.plan_contract import PlanStep, ProfessorPlan, RiskClass
from atlas_engine.tenant_membership import SQLiteMembershipRegistry
from atlas_engine.tenant_plan_repository import TenantPlanRepository


ISSUER = "https://professor-qa.test/"
CONFIG = OIDCProviderConfig(
    issuer=ISSUER, audience="atlas-api",
    jwks_uri=ISSUER + ".well-known/jwks.json",
    allowed_algorithms=frozenset({"RS256"}),
)


class Verifier:
    subject = "alice"

    def verify(self, _token):
        now = int(time.time())
        return VerifiedTokenClaims(
            issuer=ISSUER, subject=self.subject, audiences=("atlas-api",),
            expires_at=now + 300, not_before=now - 10, roles=(),
        )


def setup_client(monkeypatch, tmp_path):
    from atlas_engine import storage
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "core.sqlite"))
    storage.init_db()
    tenant_path = str(tmp_path / "tenant.sqlite")
    memberships_path = str(tmp_path / "members.sqlite")
    monkeypatch.setenv("ATLAS_TENANT_DATA_DB_PATH", tenant_path)
    monkeypatch.setenv("ATLAS_MEMBERSHIP_DB_PATH", memberships_path)
    for name in ("ATLAS_OIDC_ISSUER", "ATLAS_OIDC_AUDIENCE",
                 "ATLAS_OIDC_JWKS_URI", "ATLAS_OIDC_ALLOWED_ALGORITHMS"):
        monkeypatch.delenv(name, raising=False)
    memberships = SQLiteMembershipRegistry(memberships_path)
    memberships.initialize()
    memberships.create_tenant("tenant-a", "Tenant A")
    memberships.create_tenant("tenant-b", "Tenant B")
    memberships.provision_membership(ISSUER, "alice", "tenant-a", {"plans:read", "plans:write", "steps:read"})
    memberships.provision_membership(ISSUER, "bob", "tenant-b", {"plans:read", "steps:read"})
    memberships.provision_membership(ISSUER, "limited", "tenant-a", {"plans:read", "plans:write"})
    client = TestClient(app_module.app)
    client.__enter__()
    verifier = Verifier()
    app_module.app.state.identity_service = VerifiedIdentityService(CONFIG, verifier, memberships)

    report = {
        "schema_version": 1, "report_type": "professor_evidence_report",
        "executive_summary": {
            "claim_count": 1, "finding_count": 1, "challenge_count": 0,
            "disagreement_count": 0, "evidence_gap_count": 0, "source_count": 1,
            "confidence": "not_scored",
            "overall_conclusion": "No overall truth conclusion is drawn from annotation labels alone.",
        },
        "findings": [{
            "claim_id": "claim-1", "claim": "The sample improved outcomes",
            "status": "supported_by_supplied_annotations",
            "supporting_sources": ["source-1"], "challenging_sources": [],
            "source_references": ["source-1"], "interpretation": "Reviewer annotation only.",
        }],
        "challenges": [], "disagreements": [], "evidence_gaps": [],
        "sources": [{"source_id": "source-1", "title": "Study", "doi": "10.1234/test"}],
        "limitations": ["Annotations are not independent verification."],
    }
    db = sqlite3.connect(tenant_path)
    db.row_factory = sqlite3.Row
    principal = RequestPrincipal(ISSUER, "alice", "tenant-a", True, frozenset({"plans:read", "steps:read"}))
    TenantPlanRepository(db, principal).create(ProfessorPlan(
        "qa-plan", "Ask about a report", ("Report is available",),
        (PlanStep("report", "research.professor.report", "Build report", RiskClass.READ_ONLY),),
    ))
    db.execute("""
      INSERT INTO tenant_professor_step_runs
        (tenant_id,plan_id,step_id,state,result_json)
      VALUES(?,?,?,?,?)
    """, ("tenant-a", "qa-plan", "report", "succeeded", json.dumps(report)))
    db.commit()
    db.close()
    return client, verifier


def test_ask_endpoint_answers_from_tenant_report_only(monkeypatch, tmp_path):
    client, _ = setup_client(monkeypatch, tmp_path)
    try:
        response = client.post(
            "/professor/tenant/plans/qa-plan/ask",
            headers={"Authorization": "Bearer valid"},
            json={"question": "Show findings"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["basis"] == "findings"
        assert body["items"][0]["claim_id"] == "claim-1"
        assert body["mode"] == "deterministic_report_lookup"
        assert body["tools_invoked"] is False
        assert body["execution_performed"] is False
    finally:
        client.__exit__(None, None, None)


def test_ask_endpoint_rejects_cross_tenant_plan(monkeypatch, tmp_path):
    client, verifier = setup_client(monkeypatch, tmp_path)
    try:
        verifier.subject = "bob"
        response = client.post(
            "/professor/tenant/plans/qa-plan/ask",
            headers={"Authorization": "Bearer valid"},
            json={"question": "Show findings"},
        )
        assert response.status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_ask_endpoint_requires_plan_and_step_read_scopes(monkeypatch, tmp_path):
    client, verifier = setup_client(monkeypatch, tmp_path)
    try:
        verifier.subject = "limited"
        response = client.post(
            "/professor/tenant/plans/qa-plan/ask",
            headers={"Authorization": "Bearer valid"},
            json={"question": "Show findings"},
        )
        assert response.status_code == 403
    finally:
        client.__exit__(None, None, None)


def test_ask_endpoint_rejects_unexpected_fields_and_oversized_questions(monkeypatch, tmp_path):
    client, _ = setup_client(monkeypatch, tmp_path)
    try:
        headers = {"Authorization": "Bearer valid"}
        extra = client.post("/professor/tenant/plans/qa-plan/ask", headers=headers,
                            json={"question": "Show findings", "tenant_id": "tenant-b"})
        oversized = client.post("/professor/tenant/plans/qa-plan/ask", headers=headers,
                                json={"question": "x" * 1001})
        assert extra.status_code == 422
        assert oversized.status_code == 422
    finally:
        client.__exit__(None, None, None)
