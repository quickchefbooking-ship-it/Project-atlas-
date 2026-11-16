import hashlib
import sqlite3

from test_tenant_approved_sources_api import _setup, _stage


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
            ("https://identity.tenant-sources.test/" + "\0" + "writer").encode("utf-8")
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
