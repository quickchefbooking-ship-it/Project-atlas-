import sqlite3

import pytest

from atlas_engine.tenant_approved_sources import (
    initialize_tenant_approved_source_schema,
    review_tenant_source_document,
    stage_tenant_source_document,
)
from atlas_engine.tenant_source_assessments import (
    append_tenant_source_assessment,
    initialize_tenant_source_assessment_schema,
    list_tenant_source_assessments,
)


def _db(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    initialize_tenant_approved_source_schema(db)
    initialize_tenant_source_assessment_schema(db)
    return db


def _approved_source(db, tenant="tenant-a"):
    staged = stage_tenant_source_document(
        db, tenant_id=tenant, staged_by="reviewer:stage",
        title="Research paper", uri="https://journal.example/paper/123",
        content="<html><body><p>Research text.</p></body></html>",
    )
    review_tenant_source_document(
        db, tenant_id=tenant, document_id=staged["document_id"],
        reviewer_id="reviewer:approve", decision="approved",
        trust_level="reviewed",
    )
    db.commit()
    return staged["document_id"]


def test_source_assessments_record_publication_retraction_and_methodology_with_provenance(tmp_path):
    db = _db(tmp_path / "tenant.sqlite")
    try:
        document_id = _approved_source(db)
        result = append_tenant_source_assessment(
            db, tenant_id="tenant-a", document_id=document_id,
            reviewer_id="reviewer:assessor",
            publication_status="published",
            retraction_status="correction_notice",
            study_design="randomized_trial",
            evidence_references=["https://journal.example/correction-notice"],
            rationale="Publisher correction notice reviewed; original publication remains available.",
        )
        db.commit()
        assert result["quality_score"] == "not_scored"
        history = list_tenant_source_assessments(
            db, tenant_id="tenant-a", document_id=document_id,
        )
        assert len(history) == 1
        assert history[0]["retraction_status"] == "correction_notice"
        assert history[0]["reviewer_id"] == "reviewer:assessor"
        assert history[0]["evidence_references"] == [
            "https://journal.example/correction-notice"
        ]
    finally:
        db.close()


def test_unknown_status_is_preserved_not_assumed_clean_or_retracted(tmp_path):
    db = _db(tmp_path / "tenant.sqlite")
    try:
        document_id = _approved_source(db)
        result = append_tenant_source_assessment(
            db, tenant_id="tenant-a", document_id=document_id,
            reviewer_id="reviewer:assessor", rationale="No verified status information available.",
        )
        assert result["publication_status"] == "unknown"
        assert result["retraction_status"] == "unknown"
        assert result["study_design"] == "unknown"
    finally:
        db.close()


def test_assessment_requires_approved_source_and_tenant_ownership(tmp_path):
    db = _db(tmp_path / "tenant.sqlite")
    try:
        pending = stage_tenant_source_document(
            db, tenant_id="tenant-a", staged_by="reviewer:stage",
            title="Pending", uri="https://journal.example/pending", content="pending text",
        )
        with pytest.raises(ValueError, match="Approved source"):
            append_tenant_source_assessment(
                db, tenant_id="tenant-a", document_id=pending["document_id"],
                reviewer_id="reviewer:assessor", rationale="Pending must not be assessed.",
            )
        approved_id = _approved_source(db)
        with pytest.raises(ValueError, match="Approved source"):
            append_tenant_source_assessment(
                db, tenant_id="tenant-b", document_id=approved_id,
                reviewer_id="reviewer:assessor", rationale="Cross-tenant attempt.",
            )
    finally:
        db.close()


@pytest.mark.parametrize("kwargs", [
    {"publication_status": "verified"},
    {"retraction_status": "clear"},
    {"study_design": "high_quality"},
    {"evidence_references": ["http://journal.example/notice"]},
    {"evidence_references": ["https://user:pass@journal.example/notice"]},
    {"evidence_references": ["https://journal.example:8443/notice"]},
])
def test_assessment_rejects_uncontrolled_values_and_unsafe_evidence_references(tmp_path, kwargs):
    db = _db(tmp_path / "tenant.sqlite")
    try:
        document_id = _approved_source(db)
        with pytest.raises(ValueError):
            append_tenant_source_assessment(
                db, tenant_id="tenant-a", document_id=document_id,
                reviewer_id="reviewer:assessor", rationale="Test assessment.", **kwargs,
            )
    finally:
        db.close()


def test_assessment_history_is_append_only(tmp_path):
    db = _db(tmp_path / "tenant.sqlite")
    try:
        document_id = _approved_source(db)
        item = append_tenant_source_assessment(
            db, tenant_id="tenant-a", document_id=document_id,
            reviewer_id="reviewer:assessor", rationale="First review.",
        )
        db.commit()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute(
                "UPDATE tenant_source_assessments SET rationale='rewritten' WHERE assessment_id=?",
                (item["assessment_id"],),
            )
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute(
                "DELETE FROM tenant_source_assessments WHERE assessment_id=?",
                (item["assessment_id"],),
            )
    finally:
        db.close()


def test_assessment_history_is_tenant_scoped_and_preserves_revisions(tmp_path):
    db = _db(tmp_path / "tenant.sqlite")
    try:
        document_id = _approved_source(db)
        first = append_tenant_source_assessment(
            db, tenant_id="tenant-a", document_id=document_id,
            reviewer_id="reviewer:a", retraction_status="unknown",
            rationale="Initial review: status unknown.",
        )
        second = append_tenant_source_assessment(
            db, tenant_id="tenant-a", document_id=document_id,
            reviewer_id="reviewer:b", retraction_status="retracted",
            evidence_references=["https://journal.example/retraction"],
            rationale="Later review: publisher retraction notice located.",
        )
        db.commit()
        assert first["assessment_id"] != second["assessment_id"]
        assert len(list_tenant_source_assessments(db, tenant_id="tenant-a", document_id=document_id)) == 2
        assert list_tenant_source_assessments(db, tenant_id="tenant-b", document_id=document_id) == []
    finally:
        db.close()
