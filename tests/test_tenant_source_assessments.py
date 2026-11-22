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



def test_source_assessment_correction_supersedes_without_mutating_prior_revision(tmp_path):
    db = _db(tmp_path / "tenant.sqlite")
    try:
        document_id = _approved_source(db)
        original = append_tenant_source_assessment(
            db, tenant_id="tenant-a", document_id=document_id,
            reviewer_id="reviewer:first", retraction_status="unknown",
            rationale="Initial status unknown.",
        )
        db.commit()
        corrected = append_tenant_source_assessment(
            db, tenant_id="tenant-a", document_id=document_id,
            reviewer_id="reviewer:second", retraction_status="retracted",
            evidence_references=["https://journal.example/retraction"],
            rationale="Publisher retraction notice confirmed.",
            supersedes_assessment_id=original["assessment_id"],
            revision_reason="The first review did not have the publisher notice.",
        )
        db.commit()
        history = list_tenant_source_assessments(
            db, tenant_id="tenant-a", document_id=document_id,
        )
        by_id = {item["assessment_id"]: item for item in history}
        assert by_id[original["assessment_id"]]["status"] == "superseded"
        assert by_id[original["assessment_id"]]["superseded_by"] == corrected["assessment_id"]
        assert by_id[original["assessment_id"]]["retraction_status"] == "unknown"
        assert by_id[corrected["assessment_id"]]["status"] == "active"
        assert by_id[corrected["assessment_id"]]["supersedes_assessment_id"] == original["assessment_id"]
        assert by_id[corrected["assessment_id"]]["revision_reason"] == "The first review did not have the publisher notice."
    finally:
        db.close()


def test_assessment_correction_requires_reason_and_valid_same_source_target(tmp_path):
    db = _db(tmp_path / "tenant.sqlite")
    try:
        document_id = _approved_source(db)
        other_document_id = _approved_source(db)
        original = append_tenant_source_assessment(
            db, tenant_id="tenant-a", document_id=document_id,
            reviewer_id="reviewer:first", rationale="Original.",
        )
        with pytest.raises(ValueError, match="both supersedes"):
            append_tenant_source_assessment(
                db, tenant_id="tenant-a", document_id=document_id,
                reviewer_id="reviewer:second", rationale="Correction.",
                supersedes_assessment_id=original["assessment_id"],
            )
        with pytest.raises(ValueError, match="not found"):
            append_tenant_source_assessment(
                db, tenant_id="tenant-a", document_id=other_document_id,
                reviewer_id="reviewer:second", rationale="Cross-source correction.",
                supersedes_assessment_id=original["assessment_id"],
                revision_reason="Wrong source.",
            )
        with pytest.raises(ValueError, match="not found"):
            append_tenant_source_assessment(
                db, tenant_id="tenant-b", document_id=document_id,
                reviewer_id="reviewer:second", rationale="Cross-tenant correction.",
                supersedes_assessment_id=original["assessment_id"],
                revision_reason="Wrong tenant.",
            )
    finally:
        db.close()


def test_assessment_can_be_superseded_only_once_and_correction_chain_is_append_only(tmp_path):
    db = _db(tmp_path / "tenant.sqlite")
    try:
        document_id = _approved_source(db)
        first = append_tenant_source_assessment(
            db, tenant_id="tenant-a", document_id=document_id,
            reviewer_id="reviewer:first", rationale="First.",
        )
        second = append_tenant_source_assessment(
            db, tenant_id="tenant-a", document_id=document_id,
            reviewer_id="reviewer:second", rationale="Second.",
            supersedes_assessment_id=first["assessment_id"], revision_reason="Updated evidence.",
        )
        third = append_tenant_source_assessment(
            db, tenant_id="tenant-a", document_id=document_id,
            reviewer_id="reviewer:third", rationale="Third.",
            supersedes_assessment_id=second["assessment_id"], revision_reason="Further correction.",
        )
        with pytest.raises(ValueError, match="already been superseded"):
            append_tenant_source_assessment(
                db, tenant_id="tenant-a", document_id=document_id,
                reviewer_id="reviewer:fourth", rationale="Competing correction.",
                supersedes_assessment_id=first["assessment_id"], revision_reason="Competing update.",
            )
        db.commit()
        history = list_tenant_source_assessments(
            db, tenant_id="tenant-a", document_id=document_id,
        )
        assert [item["status"] for item in history] == ["superseded", "superseded", "active"]
        assert history[-1]["assessment_id"] == third["assessment_id"]
    finally:
        db.close()


def test_existing_assessment_table_is_migrated_for_correction_metadata(tmp_path):
    db = sqlite3.connect(tmp_path / "tenant.sqlite")
    db.row_factory = sqlite3.Row
    initialize_tenant_approved_source_schema(db)
    db.execute("""
      CREATE TABLE tenant_source_assessments (
        tenant_id TEXT NOT NULL, assessment_id TEXT NOT NULL, document_id TEXT NOT NULL,
        publication_status TEXT NOT NULL, retraction_status TEXT NOT NULL,
        study_design TEXT NOT NULL, evidence_references_json TEXT NOT NULL,
        rationale TEXT NOT NULL, reviewer_id TEXT NOT NULL, assessed_at TEXT NOT NULL,
        PRIMARY KEY(tenant_id, assessment_id),
        FOREIGN KEY(tenant_id, document_id)
          REFERENCES tenant_approved_source_documents(tenant_id, document_id)
      )
    """)
    initialize_tenant_source_assessment_schema(db)
    columns = {
        row["name"] for row in db.execute("PRAGMA table_info(tenant_source_assessments)")
    }
    assert "supersedes_assessment_id" in columns
    assert "revision_reason" in columns
    db.close()
