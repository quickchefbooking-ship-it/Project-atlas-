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
    TenantPlanRepository(db, principal).create(ProfessorPlan(
        "review-plan", "Review a completed evidence bundle",
        ("Retain explicit reviewer attribution",),
        (PlanStep(
            "bundle", "research.evidence.bundle", "Bundle the supplied source records",
            RiskClass.READ_ONLY, required_scopes=("research:public",),
            capability_version="1.0.0",
        ),),
    ))
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
