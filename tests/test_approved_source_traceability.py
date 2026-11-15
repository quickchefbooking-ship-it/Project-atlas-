import hashlib
import sqlite3

import pytest

from atlas_engine import storage
from atlas_engine.approved_source_traceability import trace_approved_source_excerpt
from atlas_engine.source_division import ingest_document, register_source, review_document


SOURCE = (
    "Title: Approved source\n"
    "Section 4\n"
    "The published analysis found a measurable association in the study sample.\n"
)


def _database(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "approved-sources.sqlite"))
    storage.init_db()
    register_source("manual-review", "Manual review", "manual_import")
    return ingest_document(
        "manual-review",
        "Approved research",
        "https://example.org/research/approved",
        SOURCE,
        metadata={"publisher": "Example Research Group"},
    )


def _trace(document_id, **overrides):
    values = {
        "source_document_id": document_id,
        "excerpt": "The published analysis found a measurable association in the study sample.",
        "locator": "Section 4, paragraph 1",
        "claim_id": "claim-17",
        "claim_text": "The analysis found an association.",
        "relation": "supports",
    }
    values.update(overrides)
    return trace_approved_source_excerpt(**values)


def test_traceability_resolves_approved_source_by_persisted_id(monkeypatch, tmp_path):
    staged = _database(monkeypatch, tmp_path)
    review_document(staged["id"], "approved", "source-review-label")

    result = _trace(staged["id"])

    expected = hashlib.sha256(SOURCE.strip().encode("utf-8")).hexdigest()
    assert result["traceability_status"] == "exact_excerpt_found"
    assert result["source_document_id"] == staged["id"]
    assert result["source_content_sha256"] == expected
    assert result["source_sha256"] == expected
    assert result["source_state"] == "approved"
    assert result["source_trust_level"] == "reviewed"
    assert result["source_reviewed_by"] == "source-review-label"
    assert "source_text" not in result


def test_pending_and_rejected_documents_cannot_be_used(monkeypatch, tmp_path):
    pending = _database(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="approved, reviewed"):
        _trace(pending["id"])

    review_document(pending["id"], "rejected", "source-review-label")
    with pytest.raises(ValueError, match="approved, reviewed"):
        _trace(pending["id"])


def test_missing_source_document_is_rejected(monkeypatch, tmp_path):
    _database(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="not found"):
        _trace("missing-document")


def test_source_snapshot_content_and_provenance_cannot_be_updated(monkeypatch, tmp_path):
    staged = _database(monkeypatch, tmp_path)
    connection = storage.get_connection()
    try:
        with pytest.raises(sqlite3.IntegrityError, match="snapshot is immutable"):
            connection.execute(
                "UPDATE source_documents SET content = ? WHERE id = ?",
                ("silently changed source", staged["id"]),
            )
        connection.rollback()
    finally:
        connection.close()


def test_source_document_snapshots_cannot_be_deleted(monkeypatch, tmp_path):
    staged = _database(monkeypatch, tmp_path)
    connection = storage.get_connection()
    try:
        with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
            connection.execute(
                "DELETE FROM source_documents WHERE id = ?", (staged["id"],)
            )
        connection.rollback()
    finally:
        connection.close()


def test_traceability_does_not_allow_caller_to_replace_source_text_or_uri(monkeypatch, tmp_path):
    staged = _database(monkeypatch, tmp_path)
    review_document(staged["id"], "approved", "source-review-label")
    with pytest.raises(TypeError):
        trace_approved_source_excerpt(
            source_document_id=staged["id"],
            source_text="forged source",
            source_uri="https://attacker.example/",
            excerpt="forged source",
            locator="page 1",
            claim_id="claim-1",
            claim_text="Forged",
            relation="supports",
        )
