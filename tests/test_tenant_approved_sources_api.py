import hashlib
import sqlite3
import time

from fastapi.testclient import TestClient

import app as app_module
from atlas_engine.http_identity import VerifiedIdentityService
from atlas_engine.oidc_contract import OIDCProviderConfig, VerifiedTokenClaims
from atlas_engine.tenant_membership import SQLiteMembershipRegistry
from atlas_engine.tenant_approved_sources import get_approved_tenant_source_document

ISSUER = "https://identity.tenant-sources.test/"
CONFIG = OIDCProviderConfig(
    issuer=ISSUER, audience="atlas-api",
    jwks_uri=ISSUER + ".well-known/jwks.json",
    allowed_algorithms=frozenset({"RS256"}),
)


class SourceVerifier:
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
    full_scopes = {"evidence:source:write", "evidence:source:approve"}
    memberships.provision_membership(ISSUER, "writer", "tenant-a", full_scopes)
    memberships.provision_membership(ISSUER, "other", "tenant-b", full_scopes)
    memberships.provision_membership(ISSUER, "no-write", "tenant-a", {"evidence:source:approve"})
    memberships.provision_membership(ISSUER, "no-approve", "tenant-a", {"evidence:source:write"})

    client = TestClient(app_module.app)
    client.__enter__()
    verifier = SourceVerifier()
    app_module.app.state.identity_service = VerifiedIdentityService(CONFIG, verifier, memberships)
    return client, verifier, tenant_path, {"Authorization": "Bearer source-test-token"}


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


def test_authenticated_source_stage_and_approval_derive_tenant_and_reviewer(monkeypatch, tmp_path):
    client, verifier, tenant_path, headers = _setup(monkeypatch, tmp_path)
    try:
        staged = _stage(client, headers)
        assert staged.status_code == 200
        staged_body = staged.json()
        assert staged_body["state"] == "pending"
        document_id = staged_body["document_id"]

        verifier.subject = "no-approve"
        denied = client.post(
            f"/professor/tenant/sources/{document_id}/review",
            headers=headers,
            json={"decision": "approved"},
        )
        assert denied.status_code == 403

        verifier.subject = "writer"
        reviewed = client.post(
            f"/professor/tenant/sources/{document_id}/review",
            headers=headers,
            json={"decision": "approved", "trust_level": "reviewed"},
        )
        assert reviewed.status_code == 200
        body = reviewed.json()
        expected = "reviewer:" + hashlib.sha256(
            (ISSUER + "\0" + "writer").encode("utf-8")
        ).hexdigest()[:32]
        assert body["reviewed_by"] == expected
        assert body["state"] == "approved"

        db = sqlite3.connect(tenant_path)
        db.row_factory = sqlite3.Row
        source = get_approved_tenant_source_document(
            db, tenant_id="tenant-a", document_id=document_id
        )
        assert source["content"] == "<html><body><p>Exact evidence excerpt.</p></body></html>"
        assert source["reviewed_by"] == expected
        assert get_approved_tenant_source_document(
            db, tenant_id="tenant-b", document_id=document_id
        ) is None
        db.close()
    finally:
        client.__exit__(None, None, None)


def test_source_routes_reject_client_supplied_tenant_and_reviewer(monkeypatch, tmp_path):
    client, _verifier, _tenant_path, headers = _setup(monkeypatch, tmp_path)
    try:
        forged_tenant = client.post(
            "/professor/tenant/sources",
            headers=headers,
            json={
                "tenant_id": "tenant-b", "title": "Source",
                "uri": "https://example.org/source", "content": "text",
            },
        )
        assert forged_tenant.status_code == 422

        staged = _stage(client, headers)
        document_id = staged.json()["document_id"]
        forged_reviewer = client.post(
            f"/professor/tenant/sources/{document_id}/review",
            headers=headers,
            json={"decision": "approved", "reviewer_id": "reviewer:forged"},
        )
        assert forged_reviewer.status_code == 422
    finally:
        client.__exit__(None, None, None)


def test_source_submission_requires_write_scope(monkeypatch, tmp_path):
    client, verifier, _tenant_path, headers = _setup(monkeypatch, tmp_path)
    try:
        verifier.subject = "no-write"
        response = _stage(client, headers)
        assert response.status_code == 403
    finally:
        client.__exit__(None, None, None)


def test_source_approval_cannot_cross_tenant_boundary(monkeypatch, tmp_path):
    client, verifier, _tenant_path, headers = _setup(monkeypatch, tmp_path)
    try:
        staged = _stage(client, headers)
        document_id = staged.json()["document_id"]
        verifier.subject = "other"
        response = client.post(
            f"/professor/tenant/sources/{document_id}/review",
            headers=headers,
            json={"decision": "approved"},
        )
        assert response.status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_source_review_rejects_invalid_uri_and_does_not_stage(monkeypatch, tmp_path):
    client, _verifier, tenant_path, headers = _setup(monkeypatch, tmp_path)
    try:
        response = client.post(
            "/professor/tenant/sources",
            headers=headers,
            json={
                "title": "Unsafe source", "uri": "http://example.org/source",
                "content": "Untrusted content",
            },
        )
        assert response.status_code == 422
        db = sqlite3.connect(tenant_path)
        count = db.execute(
            "SELECT COUNT(*) FROM tenant_approved_source_documents"
        ).fetchone()[0]
        db.close()
        assert count == 0
    finally:
        client.__exit__(None, None, None)
