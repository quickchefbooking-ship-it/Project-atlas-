import json

from fastapi.testclient import TestClient

import app as app_module
from atlas_engine import storage
from atlas_engine.source_division import register_source, review_document


def _client(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "source-api.db"))
    storage.init_db()
    monkeypatch.setattr(app_module, "API_REQUIRE_AUTH", True)
    monkeypatch.setattr(app_module, "API_KEY", "source-api-test-key")
    monkeypatch.delenv("ATLAS_API_KEY", raising=False)
    return TestClient(app_module.app)


def _headers():
    return {"X-API-Key": "source-api-test-key"}


def test_source_catalogue_and_document_queue_require_auth_and_hide_content(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    register_source("pasted-research", "Pasted Research", "manual_import")
    from atlas_engine.source_division import ingest_document
    ingest_document(
        "pasted-research", "Pending note", "https://example.org/pending",
        "This full body must not be returned by the catalogue endpoint.",
        metadata={"publisher": "Example Institute"},
    )

    assert client.get("/sources").status_code == 401
    sources = client.get("/sources", headers=_headers())
    queue = client.get("/sources/documents?state=pending", headers=_headers())

    assert sources.status_code == 200
    assert sources.json()[0]["id"] == "pasted-research"
    assert queue.status_code == 200
    assert queue.json()[0]["state"] == "pending"
    assert queue.json()[0]["uri"] == "https://example.org/pending"
    assert "content" not in queue.json()[0]


def test_pasted_import_stages_pending_and_only_approved_content_is_searchable(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    register_source("manual-research", "Manual Research", "manual_import")
    payload = {
        "source_id": "manual-research",
        "payload": {
            "schema_version": 1,
            "documents": [{
                "title": "Retrieval safety guide",
                "uri": "https://example.org/retrieval-safety",
                "content": "Approved research explains safe retrieval and provenance tracking.",
                "metadata": {"publisher": "Example Institute", "retrieved_at": "2026-11-13"},
            }],
        },
    }

    imported = client.post("/sources/import", headers=_headers(), json=payload)
    assert imported.status_code == 200
    staged = imported.json()["documents"][0]
    assert imported.json()["status"] == "staged_for_review"
    assert staged["state"] == "pending"
    assert staged["trust_level"] == "unverified"
    assert client.get("/sources/search?q=retrieval", headers=_headers()).json() == []

    review_document(staged["id"], "approved", "test-reviewer")
    results = client.get("/sources/search?q=retrieval", headers=_headers())

    assert results.status_code == 200
    assert len(results.json()) == 1
    assert results.json()[0]["uri"] == "https://example.org/retrieval-safety"
    assert results.json()[0]["content_sha256"] == staged["content_sha256"]


def test_source_import_rejects_invalid_batch_without_partial_writes(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    register_source("manual-research", "Manual Research", "manual_import")
    response = client.post("/sources/import", headers=_headers(), json={
        "source_id": "manual-research",
        "payload": {
            "schema_version": 1,
            "documents": [
                {"title": "Valid first", "uri": "https://example.org/one", "content": "Valid content."},
                {"title": "Unsafe second", "uri": "file:///etc/passwd", "content": "Must be rejected."},
            ],
        },
    })

    assert response.status_code == 422
    assert storage.list_source_documents(limit=100) == []


def test_source_document_queue_validates_state_and_limit(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    assert client.get("/sources/documents?state=unknown", headers=_headers()).status_code == 422
    assert client.get("/sources/documents?limit=101", headers=_headers()).status_code == 422


def test_professor_source_interface_is_served_and_manual_source_is_bootstrapped(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    with client:
        page = client.get("/professor/sources")

    assert page.status_code == 200
    assert "Source Division" in page.text
    assert "Stage import for review" in page.text
    assert "localStorage" not in page.text
    assert storage.get_source("manual-paste") is not None
