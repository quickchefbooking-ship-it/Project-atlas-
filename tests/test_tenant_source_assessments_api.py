import hashlib
import sqlite3
import time

from fastapi.testclient import TestClient

import app as app_module
from atlas_engine.http_identity import VerifiedIdentityService
from atlas_engine.oidc_contract import OIDCProviderConfig, VerifiedTokenClaims
from atlas_engine.tenant_membership import SQLiteMembershipRegistry

ISSUER = "https://identity.tenant-sources.test/"
CONFIG = OIDCProviderConfig(
    issuer=ISSUER, audience="atlas-api",
    jwks_uri=ISSUER + ".well-known/jwks.json",
    allowed_algorithms=frozenset({"RS256"}),
)


class SourceAssessmentVerifier:
    def __init__(self):
        self.subject = "writer"

    def verify(self, _token):
        now = int(time.time())
        return VerifiedTokenClaims(
            issuer=ISSUER, subject=self.subject, audiences=("atlas-api",),
            expires_at=now + 300, not_before=now - 10, roles=(),
        )


def _setup(monkeypatch, tmp_path):
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
    memberships.create_tenant("tenant-b", "Tenant B")
    full_scopes = {"evidence:source:write", "evidence:source:approve", "evidence:source:assess"}
    memberships.provision_membership(ISSUER, "writer", "tenant-a", full_scopes)
    memberships.provision_membership(ISSUER, "other", "tenant-b", full_scopes)
    memberships.provision_membership(
        ISSUER, "no-assess", "tenant-a",
        {"evidence:source:write", "evidence:source:approve"},
    )
    client = TestClient(app_module.app)
    client.__enter__()
    verifier = SourceAssessmentVerifier()
    app_module.app.state.identity_service = VerifiedIdentityService(CONFIG, verifier, memberships)
    return client, verifier, tenant_path, {"Authorization": "Bearer source-assessment-token"}


def _stage(client, headers):
    return client.post(
        "/professor/tenant/sources",
        headers=headers,
        json={
            "title": "Approved HTML source",
            "uri": "https://example.org/evidence",
            "content": "<html><body><p>Exact evidence excerpt.</p></body></html>",
            "content_type": "text/html",
            "metadata": {"publisher": "Example Institute"},
        },
    )


def _approved(client, headers):
    staged = _stage(client, headers)
    assert staged.status_code == 200
    document_id = staged.json()["document_id"]
    reviewed = client.post(
        f"/professor/tenant/sources/{document_id}/review",
        headers=headers,
        json={"decision": "approved", "trust_level": "reviewed"},
    )
    assert reviewed.status_code == 200
    return document_id


def test_authenticated_source_assessment_is_attributed_and_append_only(monkeypatch, tmp_path):
    client, verifier, tenant_path, headers = _setup(monkeypatch, tmp_path)
    try:
        document_id = _approved(client, headers)
        response = client.post(
            f"/professor/tenant/sources/{document_id}/assessments",
            headers=headers,
            json={
                "publication_status": "published",
                "retraction_status": "correction_notice",
                "study_design": "randomized_trial",
                "evidence_references": ["https://example.org/correction"],
                "rationale": "Publisher correction notice reviewed.",
            },
        )
        assert response.status_code == 200
        body = response.json()
        expected = "reviewer:" + hashlib.sha256(
            (ISSUER + "\0" + "writer").encode("utf-8")
        ).hexdigest()[:32]
        assert body["reviewer_id"] == expected
        assert body["retraction_status"] == "correction_notice"
        assert body["quality_score"] == "not_scored"
        db = sqlite3.connect(tenant_path)
        rows = db.execute(
            "SELECT COUNT(*) FROM tenant_source_assessments WHERE tenant_id='tenant-a' AND document_id=?",
            (document_id,),
        ).fetchone()[0]
        db.close()
        assert rows == 1
    finally:
        client.__exit__(None, None, None)


def test_source_assessment_requires_dedicated_scope(monkeypatch, tmp_path):
    client, verifier, _tenant_path, headers = _setup(monkeypatch, tmp_path)
    try:
        document_id = _approved(client, headers)
        verifier.subject = "no-assess"
        response = client.post(
            f"/professor/tenant/sources/{document_id}/assessments",
            headers=headers,
            json={"rationale": "No permission."},
        )
        assert response.status_code == 403
    finally:
        client.__exit__(None, None, None)


def test_source_assessment_rejects_caller_supplied_identity_and_unverified_status(monkeypatch, tmp_path):
    client, _verifier, _tenant_path, headers = _setup(monkeypatch, tmp_path)
    try:
        document_id = _approved(client, headers)
        forged = client.post(
            f"/professor/tenant/sources/{document_id}/assessments",
            headers=headers,
            json={"rationale": "Forged.", "reviewer_id": "reviewer:forged", "tenant_id": "tenant-b"},
        )
        unsupported = client.post(
            f"/professor/tenant/sources/{document_id}/assessments",
            headers=headers,
            json={"rationale": "Unsupported.", "retraction_status": "clear"},
        )
        assert forged.status_code == 422
        assert unsupported.status_code == 422
    finally:
        client.__exit__(None, None, None)


def test_source_assessment_cannot_access_other_tenant_or_pending_source(monkeypatch, tmp_path):
    client, verifier, _tenant_path, headers = _setup(monkeypatch, tmp_path)
    try:
        staged = _stage(client, headers)
        document_id = staged.json()["document_id"]
        pending = client.post(
            f"/professor/tenant/sources/{document_id}/assessments",
            headers=headers, json={"rationale": "Pending source."},
        )
        verifier.subject = "other"
        cross_tenant = client.post(
            f"/professor/tenant/sources/{document_id}/assessments",
            headers=headers, json={"rationale": "Cross-tenant."},
        )
        assert pending.status_code == 404
        assert cross_tenant.status_code == 404
    finally:
        client.__exit__(None, None, None)
