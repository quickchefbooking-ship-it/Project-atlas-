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
from atlas_engine.tenant_step_execution_repository import TenantStepExecutionRepository


ISSUER = "https://identity.evidence-review.test/"
CONFIG = OIDCProviderConfig(
    issuer=ISSUER, audience="atlas-api",
    jwks_uri=ISSUER + ".well-known/jwks.json",
    allowed_algorithms=frozenset({"RS256"}),
)


class ReviewVerifier:
    def __init__(self):
        self.subject = "reviewer-a"

    def verify(self, _token):
        now = int(time.time())
        return VerifiedTokenClaims(
            issuer=ISSUER, subject=self.subject, audiences=("atlas-api",),
            expires_at=now + 300, not_before=now - 10, roles=(),
        )


def _client(monkeypatch, tmp_path, *, review_scope=True):
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
    scopes = {"plans:read", "plans:write", "steps:read", "evidence:review"}
    if not review_scope:
        scopes.remove("evidence:review")
    memberships.provision_membership(ISSUER, "reviewer-a", "tenant-a", scopes)
    client = TestClient(app_module.app)
    client.__enter__()
    verifier = ReviewVerifier()
    app_module.app.state.identity_service = VerifiedIdentityService(CONFIG, verifier, memberships)

    db = sqlite3.connect(tenant_path)
    db.row_factory = sqlite3.Row
    principal = RequestPrincipal(ISSUER, "reviewer-a", "tenant-a", True, frozenset(scopes))
    steps = TenantStepExecutionRepository(db, principal)
    TenantPlanRepository(db, principal).create(ProfessorPlan(
        "review-plan", "Review a completed evidence bundle",
        ("Retain explicit reviewer attribution",),
        (
            PlanStep(
                "bundle", "research.evidence.bundle", "Bundle the supplied source records",
                RiskClass.READ_ONLY, required_scopes=("research:public",),
                capability_version="1.0.0",
            ),
            PlanStep(
                "evaluate", "research.evidence.evaluate", "Evaluate reviewed annotations",
                RiskClass.READ_ONLY, depends_on=("bundle",),
                required_scopes=("research:public",), capability_version="1.0.0",
            ),
            PlanStep(
                "report", "research.professor.report", "Create a source-linked report",
                RiskClass.READ_ONLY, depends_on=("bundle", "evaluate"),
                required_scopes=("research:public",), capability_version="1.0.0",
            ),
        ),
    ))
    TenantStepExecutionRepository(db, principal).list_steps("review-plan")
    bundle = {
        "schema_version": 1,
        "summary": {"source_count": 1, "claim_count": 0, "confidence": "not_scored"},
        "sources": [{"source_id": "source-1", "title": "Test source"}],
        "claims": [],
        "limitations": [],
    }
    db.execute("""
      INSERT INTO tenant_professor_step_runs
        (tenant_id,plan_id,step_id,state,result_json)
      VALUES(?,?,?,?,?)
    """, ("tenant-a", "review-plan", "bundle", "succeeded",
          json.dumps(bundle, separators=(",", ":"))))
    db.commit()
    db.close()
    return client, verifier, {"Authorization": "Bearer review-token"}


def test_review_endpoint_persists_server_attributed_annotation(monkeypatch, tmp_path):
    client, _verifier, headers = _client(monkeypatch, tmp_path)
    try:
        response = client.post(
            "/professor/tenant/plans/review-plan/evidence/bundle/review",
            headers=headers,
            json={"annotations": [{
                "claim_id": "claim-1", "text": "The source makes this claim",
                "source_id": "source-1", "relation": "supports",
            }]},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "review_recorded"
        assert body["revision"] == 1
        annotation = body["bundle"]["claims"][0]["annotations"][0]
        assert annotation["reviewer_id"].startswith("reviewer:")
        assert annotation["reviewed_at"] == body["reviewed_at"]
        assert annotation["relation"] == "supports"

        fetched = client.get(
            "/professor/tenant/plans/review-plan/evidence/bundle/review",
            headers=headers,
        )
        assert fetched.status_code == 200
        assert fetched.json()["status"] == "reviewed"
        assert fetched.json()["bundle"] == body["bundle"]
    finally:
        client.__exit__(None, None, None)


def test_review_endpoint_rejects_client_supplied_reviewer_identity(monkeypatch, tmp_path):
    client, _verifier, headers = _client(monkeypatch, tmp_path)
    try:
        response = client.post(
            "/professor/tenant/plans/review-plan/evidence/bundle/review",
            headers=headers,
            json={"reviewer_id": "forged", "annotations": [{
                "claim_id": "claim-1", "text": "A claim",
                "source_id": "source-1", "relation": "supports",
            }]},
        )
        assert response.status_code == 422
    finally:
        client.__exit__(None, None, None)


def test_review_endpoint_requires_explicit_review_scope(monkeypatch, tmp_path):
    client, _verifier, headers = _client(monkeypatch, tmp_path, review_scope=False)
    try:
        response = client.get(
            "/professor/tenant/plans/review-plan/evidence/bundle/review",
            headers=headers,
        )
        assert response.status_code == 403
    finally:
        client.__exit__(None, None, None)



def test_downstream_dependency_handoff_uses_latest_review_revision(monkeypatch, tmp_path):
    client, _verifier, headers = _client(monkeypatch, tmp_path)
    try:
        submitted = client.post(
            "/professor/tenant/plans/review-plan/evidence/bundle/review",
            headers=headers,
            json={"annotations": [{
                "claim_id": "claim-1", "text": "The source explicitly supports this",
                "source_id": "source-1", "relation": "supports",
            }]},
        )
        assert submitted.status_code == 200

        tenant_path = str(tmp_path / "tenant.sqlite")
        db = sqlite3.connect(tenant_path)
        db.row_factory = sqlite3.Row
        principal = RequestPrincipal(
            ISSUER, "reviewer-a", "tenant-a", True,
            frozenset({"steps:read", "evidence:review"}),
        )
        dependencies = TenantStepExecutionRepository(db, principal).dependency_results(
            "review-plan", "evaluate"
        )
        reviewed_bundle = dependencies["bundle"]
        assert reviewed_bundle["claims"][0]["claim_id"] == "claim-1"
        assert reviewed_bundle["claims"][0]["annotations"][0]["reviewer_id"].startswith("reviewer:")

        runtime = app_module.build_default_capability_runtime()
        capability_input = runtime.input_for_objective(
            "research.evidence.evaluate", "1.0.0", "Evaluate reviewed annotations",
            dependency_outputs=dependencies,
        )
        assert capability_input["bundle"] == reviewed_bundle
        assert capability_input["bundle"]["claims"][0]["annotations"][0]["relation"] == "supports"

        # The completed execution output remains the original, unreviewed bundle.
        original = db.execute("""
          SELECT result_json FROM tenant_professor_step_runs
          WHERE tenant_id='tenant-a' AND plan_id='review-plan' AND step_id='bundle'
        """).fetchone()
        assert json.loads(original["result_json"])["claims"] == []
        db.close()
    finally:
        client.__exit__(None, None, None)



def test_ask_professor_answers_only_from_completed_tenant_report(monkeypatch, tmp_path):
    client, _verifier, headers = _client(monkeypatch, tmp_path)
    try:
        report = {
            "schema_version": 1,
            "report_type": "professor_evidence_report",
            "executive_summary": {
                "claim_count": 1, "finding_count": 1, "challenge_count": 0,
                "disagreement_count": 0, "evidence_gap_count": 0,
                "source_count": 1, "overall_conclusion":
                    "No overall truth conclusion is drawn from annotation labels alone.",
            },
            "findings": [{
                "claim_id": "claim-1", "claim": "The source supports kitchen temperature checks",
                "status": "supported_by_supplied_annotations",
                "supporting_sources": ["source-1"], "challenging_sources": [],
                "mentioning_sources": [], "interpretation": "Reviewer annotation supports checks.",
            }],
            "challenges": [], "disagreements": [], "evidence_gaps": [],
            "limitations": ["Supplied annotations are not independently verified."],
        }
        tenant_path = str(tmp_path / "tenant.sqlite")
        db = sqlite3.connect(tenant_path)
        db.execute("""
          INSERT INTO tenant_professor_step_runs
            (tenant_id,plan_id,step_id,state,result_json)
          VALUES('tenant-a','review-plan','report','succeeded',?)
          ON CONFLICT(tenant_id,plan_id,step_id)
          DO UPDATE SET state='succeeded',result_json=excluded.result_json
        """, (json.dumps(report),))
        db.commit()
        db.close()

        response = client.post(
            "/professor/tenant/plans/review-plan/ask",
            headers=headers,
            json={"question": "What does the report say about kitchen temperature checks?"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["answer_type"] == "matched_report_records"
        assert body["mode"] == "deterministic_report_lookup"
        assert body["matches"][0]["claim_id"] == "claim-1"
        assert body["matches"][0]["supporting_sources"] == ["source-1"]
        assert "not independent verification" in body["answer"]
        assert body["limitations"] == ["Supplied annotations are not independently verified."]
    finally:
        client.__exit__(None, None, None)


def test_ask_professor_refuses_when_report_is_not_complete(monkeypatch, tmp_path):
    client, _verifier, headers = _client(monkeypatch, tmp_path)
    try:
        response = client.post(
            "/professor/tenant/plans/review-plan/ask",
            headers=headers,
            json={"question": "Give me the summary"},
        )
        assert response.status_code == 409
    finally:
        client.__exit__(None, None, None)


def test_ask_professor_rejects_unexpected_fields_and_oversized_question(monkeypatch, tmp_path):
    client, _verifier, headers = _client(monkeypatch, tmp_path)
    try:
        unexpected = client.post(
            "/professor/tenant/plans/review-plan/ask",
            headers=headers,
            json={"question": "Summary", "tenant_id": "tenant-b"},
        )
        oversized = client.post(
            "/professor/tenant/plans/review-plan/ask",
            headers=headers,
            json={"question": "x" * 1001},
        )
        assert unexpected.status_code == 422
        assert oversized.status_code == 422
    finally:
        client.__exit__(None, None, None)
