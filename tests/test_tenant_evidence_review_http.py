import hashlib
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
    scopes = {"plans:read", "plans:write", "steps:read", "evidence:review", "evidence:source:write", "evidence:source:approve"}
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
      UPDATE tenant_professor_step_runs
      SET state='succeeded',result_json=?
      WHERE tenant_id=? AND plan_id=? AND step_id=?
    """, (json.dumps(bundle, separators=(",", ":")), "tenant-a", "review-plan", "bundle"))
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
        expected_reviewer = "reviewer:" + hashlib.sha256(
            (ISSUER + "\0" + "reviewer-a").encode("utf-8")
        ).hexdigest()[:32]
        assert annotation["reviewer_id"] == expected_reviewer
        assert body["reviewer_id"] == expected_reviewer
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


def _set_bundle_source_uri(tmp_path, uri):
    tenant_path = str(tmp_path / "tenant.sqlite")
    db = sqlite3.connect(tenant_path)
    row = db.execute("""
      SELECT result_json FROM tenant_professor_step_runs
      WHERE tenant_id='tenant-a' AND plan_id='review-plan' AND step_id='bundle'
    """).fetchone()
    bundle = json.loads(row[0])
    bundle["sources"][0]["uri"] = uri
    db.execute("""
      UPDATE tenant_professor_step_runs SET result_json=?
      WHERE tenant_id='tenant-a' AND plan_id='review-plan' AND step_id='bundle'
    """, (json.dumps(bundle, separators=(",", ":")),))
    db.commit()
    db.close()


def test_review_links_annotation_to_exact_approved_tenant_html_excerpt(monkeypatch, tmp_path):
    client, _verifier, headers = _client(monkeypatch, tmp_path)
    source_uri = "https://evidence.example.test/kitchen-checks"
    excerpt = "Temperature records were checked daily."
    try:
        staged = client.post(
            "/professor/tenant/sources", headers=headers,
            json={
                "title": "Kitchen temperature checks",
                "uri": source_uri,
                "content": "<html><body><p>Temperature records were checked daily.</p></body></html>",
                "content_type": "text/html",
            },
        )
        assert staged.status_code == 200
        document_id = staged.json()["document_id"]
        approved = client.post(
            f"/professor/tenant/sources/{document_id}/review",
            headers=headers, json={"decision": "approved", "trust_level": "reviewed"},
        )
        assert approved.status_code == 200
        _set_bundle_source_uri(tmp_path, source_uri)

        response = client.post(
            "/professor/tenant/plans/review-plan/evidence/bundle/review",
            headers=headers,
            json={"annotations": [{
                "claim_id": "claim-1", "text": "Temperature checks were completed",
                "source_id": "source-1", "relation": "supports",
                "source_document_id": document_id, "excerpt": excerpt,
            }]},
        )
        assert response.status_code == 200
        annotation = response.json()["bundle"]["claims"][0]["annotations"][0]
        traceability = annotation["source_traceability"]
        assert traceability["source_document_id"] == document_id
        assert traceability["source_uri"] == source_uri
        assert traceability["source_state"] == "approved"
        assert traceability["locator_status"] == "exact_excerpt_found"
        assert traceability["locator"] == "html/html[1]/body[1]/p[1]"
        assert traceability["reviewer_identity_verified"] is False
        assert "does not establish claim support" in response.json()["bundle"]["limitations"][-1]
    finally:
        client.__exit__(None, None, None)


def test_review_rejects_excerpt_from_pending_tenant_source(monkeypatch, tmp_path):
    client, _verifier, headers = _client(monkeypatch, tmp_path)
    source_uri = "https://evidence.example.test/pending"
    try:
        staged = client.post(
            "/professor/tenant/sources", headers=headers,
            json={
                "title": "Pending source", "uri": source_uri,
                "content": "<html><body><p>Pending excerpt.</p></body></html>",
                "content_type": "text/html",
            },
        )
        assert staged.status_code == 200
        document_id = staged.json()["document_id"]
        _set_bundle_source_uri(tmp_path, source_uri)
        response = client.post(
            "/professor/tenant/plans/review-plan/evidence/bundle/review",
            headers=headers,
            json={"annotations": [{
                "claim_id": "claim-1", "text": "Pending excerpt",
                "source_id": "source-1", "relation": "supports",
                "source_document_id": document_id, "excerpt": "Pending excerpt.",
            }]},
        )
        assert response.status_code == 422
        assert "Approved tenant HTML source document was not found" in response.json()["detail"]
    finally:
        client.__exit__(None, None, None)


def test_review_rejects_bundle_source_uri_mismatch(monkeypatch, tmp_path):
    client, _verifier, headers = _client(monkeypatch, tmp_path)
    source_uri = "https://evidence.example.test/approved"
    try:
        staged = client.post(
            "/professor/tenant/sources", headers=headers,
            json={
                "title": "Approved source", "uri": source_uri,
                "content": "<html><body><p>Unique excerpt.</p></body></html>",
                "content_type": "text/html",
            },
        )
        document_id = staged.json()["document_id"]
        approved = client.post(
            f"/professor/tenant/sources/{document_id}/review",
            headers=headers, json={"decision": "approved", "trust_level": "reviewed"},
        )
        assert approved.status_code == 200
        _set_bundle_source_uri(tmp_path, "https://different.example.test/source")
        response = client.post(
            "/professor/tenant/plans/review-plan/evidence/bundle/review",
            headers=headers,
            json={"annotations": [{
                "claim_id": "claim-1", "text": "Unique excerpt",
                "source_id": "source-1", "relation": "supports",
                "source_document_id": document_id, "excerpt": "Unique excerpt.",
            }]},
        )
        assert response.status_code == 422
        assert "does not match the evidence bundle source" in response.json()["detail"]
    finally:
        client.__exit__(None, None, None)


def test_review_correction_supersedes_annotation_without_rewriting_prior_revision(monkeypatch, tmp_path):
    client, _verifier, headers = _client(monkeypatch, tmp_path)
    try:
        initial = client.post(
            "/professor/tenant/plans/review-plan/evidence/bundle/review",
            headers=headers,
            json={"annotations": [{
                "claim_id": "claim-1", "text": "The source makes this claim",
                "source_id": "source-1", "relation": "supports",
            }]},
        )
        assert initial.status_code == 200
        initial_body = initial.json()
        old_annotation = initial_body["bundle"]["claims"][0]["annotations"][0]
        old_id = old_annotation["annotation_id"]
        assert initial_body["revision_kind"] == "initial"
        assert old_annotation["status"] == "active"

        corrected = client.post(
            "/professor/tenant/plans/review-plan/evidence/bundle/review",
            headers=headers,
            json={"annotations": [{
                "claim_id": "claim-1", "text": "The source makes this claim",
                "source_id": "source-1", "relation": "challenges",
                "supersedes_annotation_id": old_id,
                "correction_reason": "On re-reading the source, the earlier interpretation was incorrect.",
            }]},
        )
        assert corrected.status_code == 200
        body = corrected.json()
        assert body["revision"] == 2
        assert body["revision_kind"] == "correction"
        assert body["supersedes_review_id"] == 1
        assert "earlier interpretation was incorrect" in body["revision_reason"]

        annotations = body["bundle"]["claims"][0]["annotations"]
        old = next(item for item in annotations if item["annotation_id"] == old_id)
        new = next(item for item in annotations if item["relation"] == "challenges")
        assert old["status"] == "superseded"
        assert old["superseded_by"] == new["annotation_id"]
        assert old["superseded_by_reviewer_id"].startswith("reviewer:")
        assert new["status"] == "active"
        assert new["supersedes_annotation_id"] == old_id
        assert "earlier interpretation was incorrect" in new["correction_reason"]

        tenant_path = str(tmp_path / "tenant.sqlite")
        db = sqlite3.connect(tenant_path)
        rows = db.execute("""
          SELECT review_id,bundle_json,supersedes_review_id,revision_kind
          FROM tenant_evidence_reviews
          WHERE tenant_id='tenant-a' AND plan_id='review-plan' AND bundle_step_id='bundle'
          ORDER BY review_id
        """).fetchall()
        db.close()
        assert len(rows) == 2
        assert rows[0][0] == 1 and rows[0][2] is None and rows[0][3] == "initial"
        prior_bundle = json.loads(rows[0][1])
        prior_annotation = prior_bundle["claims"][0]["annotations"][0]
        assert prior_annotation["status"] == "active"
        assert "superseded_by" not in prior_annotation
        assert rows[1][2] == 1 and rows[1][3] == "correction"
    finally:
        client.__exit__(None, None, None)


def test_review_correction_requires_existing_same_claim_source_and_reason(monkeypatch, tmp_path):
    client, _verifier, headers = _client(monkeypatch, tmp_path)
    try:
        initial = client.post(
            "/professor/tenant/plans/review-plan/evidence/bundle/review",
            headers=headers,
            json={"annotations": [{
                "claim_id": "claim-1", "text": "The source makes this claim",
                "source_id": "source-1", "relation": "supports",
            }]},
        )
        old_id = initial.json()["bundle"]["claims"][0]["annotations"][0]["annotation_id"]
        invalid = client.post(
            "/professor/tenant/plans/review-plan/evidence/bundle/review",
            headers=headers,
            json={"annotations": [{
                "claim_id": "different-claim", "text": "Different claim",
                "source_id": "source-1", "relation": "challenges",
                "supersedes_annotation_id": old_id,
                "correction_reason": "Attempt to alter another claim.",
            }]},
        )
        missing_reason = client.post(
            "/professor/tenant/plans/review-plan/evidence/bundle/review",
            headers=headers,
            json={"annotations": [{
                "claim_id": "claim-1", "text": "The source makes this claim",
                "source_id": "source-1", "relation": "challenges",
                "supersedes_annotation_id": old_id,
            }]},
        )
        assert invalid.status_code == 422
        assert "same claim and source" in invalid.json()["detail"]
        assert missing_reason.status_code == 422
    finally:
        client.__exit__(None, None, None)


def test_review_schema_adds_supersession_columns_to_existing_history_table():
    from atlas_engine.tenant_evidence_review import initialize_tenant_evidence_review_schema

    db = sqlite3.connect(":memory:")
    db.execute("""
      CREATE TABLE tenant_evidence_reviews (
        review_id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id TEXT NOT NULL,
        plan_id TEXT NOT NULL,
        bundle_step_id TEXT NOT NULL,
        reviewer_id TEXT NOT NULL,
        reviewed_at TEXT NOT NULL,
        bundle_json TEXT NOT NULL,
        annotation_count INTEGER NOT NULL
      )
    """)
    initialize_tenant_evidence_review_schema(db)
    columns = {row[1] for row in db.execute("PRAGMA table_info(tenant_evidence_reviews)")}
    assert {"supersedes_review_id", "revision_kind", "revision_reason"}.issubset(columns)
    db.close()
