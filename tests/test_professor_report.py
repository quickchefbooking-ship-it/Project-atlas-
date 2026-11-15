import pytest

from atlas_engine.professor_report import build_professor_report


def bundle():
    return {
        "schema_version": 1,
        "sources": [
            {"source_id": "source-1", "title": "Study A", "uri": "https://doi.org/10.1000/a", "doi": "10.1000/a", "publisher": "Press A", "retrieved_at": "2026-11-14"},
            {"source_id": "source-2", "title": "Study B", "uri": "https://doi.org/10.1000/b", "doi": "10.1000/b", "publisher": "Press B", "retrieved_at": "2026-11-14"},
        ],
        "claims": [],
        "duplicate_records": [{"source_ids": ["source-1", "source-2"], "notice": "duplicate"}],
        "limitations": ["No independent verification."],
    }


def evaluation():
    return {
        "schema_version": 1,
        "evaluations": [
            {"claim_id": "c1", "text": "Claim one", "status": "supported_by_supplied_annotations", "supporting_source_ids": ["source-1"], "challenging_source_ids": [], "mentioning_source_ids": [], "confidence": "not_scored", "interpretation": "Annotation only."},
            {"claim_id": "c2", "text": "Claim two", "status": "challenged_by_supplied_annotations", "supporting_source_ids": [], "challenging_source_ids": ["source-2"], "mentioning_source_ids": [], "confidence": "not_scored", "interpretation": "Annotation only."},
            {"claim_id": "c3", "text": "Claim three", "status": "conflicting_annotations", "supporting_source_ids": ["source-1"], "challenging_source_ids": ["source-2"], "mentioning_source_ids": [], "confidence": "not_scored", "interpretation": "Annotation only."},
            {"claim_id": "c4", "text": "Claim four", "status": "insufficient_evidence", "supporting_source_ids": [], "challenging_source_ids": [], "mentioning_source_ids": [], "confidence": "not_scored", "interpretation": "No annotations."},
        ],
        "limitations": ["No confidence scoring."],
    }


def test_report_separates_findings_challenges_disagreements_and_gaps():
    report = build_professor_report(bundle(), evaluation())
    assert len(report["findings"]) == 1
    assert len(report["challenges"]) == 1
    assert len(report["disagreements"]) == 1
    assert len(report["evidence_gaps"]) == 1
    assert report["executive_summary"]["claim_count"] == 4
    assert report["executive_summary"]["confidence"] == "not_scored"


def test_report_preserves_source_references_and_source_metadata():
    report = build_professor_report(bundle(), evaluation())
    finding = report["findings"][0]
    assert finding["source_references"] == ["source-1"]
    assert report["sources"][0]["title"] == "Study A"
    assert report["duplicate_records"][0]["source_ids"] == ["source-1", "source-2"]


def test_report_rejects_evaluation_source_reference_missing_from_bundle():
    result = evaluation()
    result["evaluations"][0]["supporting_source_ids"] = ["source-404"]
    with pytest.raises(ValueError, match="absent from its evidence bundle"):
        build_professor_report(bundle(), result)


def test_report_rejects_unsupported_evaluation_status():
    result = evaluation()
    result["evaluations"][0]["status"] = "verified_true"
    with pytest.raises(ValueError, match="unsupported evaluation status"):
        build_professor_report(bundle(), result)
