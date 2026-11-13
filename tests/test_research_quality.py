import pytest

from atlas_engine.research_evidence import ResearchReport
from atlas_engine.research_quality import assess_evidence_quality


def _report():
    return {
        "task_id": "quality-task-1",
        "summary": "Two sources describe the approach.",
        "recommendation": "Proceed provisionally and verify details.",
        "claims": [
            {"claim_id": "claim-1", "statement": "Two sources document the approach.",
             "evidence_ids": ["evidence-1", "evidence-2"], "status": "supported", "confidence": 0.8},
            {"claim_id": "claim-2", "statement": "Cost is not established.",
             "evidence_ids": ["evidence-1"], "status": "unknown", "confidence": 0.2},
        ],
        "evidence": [
            {"evidence_id": "evidence-1", "source_id": "publisher-a", "title": "Source A",
             "uri": "https://example.org/a", "content_sha256": "a" * 64,
             "trust_level": "reviewed", "review_state": "approved",
             "retrieved_at": "2026-11-13T10:00:00Z"},
            {"evidence_id": "evidence-2", "source_id": "publisher-b", "title": "Source B",
             "uri": "https://example.net/b", "content_sha256": "b" * 64,
             "trust_level": "authoritative", "review_state": "approved",
             "retrieved_at": "2026-11-13T10:01:00Z"},
        ],
        "uncertainty": ["Costs vary."],
        "limitations": ["No live deployment test."],
    }


def test_quality_reports_dimensions_without_truth_score():
    result = assess_evidence_quality(ResearchReport.model_validate(_report()))

    assert result["quality_score"] is None
    assert result["truth_assessed"] is False
    assert result["semantic_support_assessed"] is False
    assert result["dimensions"]["source_diversity"]["status"] == "multiple_sources"
    assert result["dimensions"]["review_state"]["status"] == "approved_metadata"
    assert result["dimensions"]["uncertainty_and_limitations"]["status"] == "documented"
    assert result["warnings"] == []


def test_quality_flags_single_source_and_uncited_evidence():
    data = _report()
    data["claims"][0]["evidence_ids"] = ["evidence-1"]
    report = ResearchReport.model_validate(data)
    result = assess_evidence_quality(report)

    assert result["dimensions"]["source_diversity"]["status"] == "single_source"
    assert result["dimensions"]["provenance"]["uncited_evidence_ids"] == ["evidence-2"]
    assert any("one distinct source" in warning for warning in result["warnings"])
    assert any("not cited" in warning for warning in result["warnings"])


def test_quality_flags_pending_unverified_and_missing_context():
    data = _report()
    data["evidence"][0]["trust_level"] = "unverified"
    data["evidence"][0]["review_state"] = "pending"
    data["claims"][0]["status"] = "provisional"
    data["claims"][0]["evidence_ids"] = ["evidence-1"]
    data["claims"][1]["evidence_ids"] = ["evidence-1"]
    data["uncertainty"] = []
    data["limitations"] = []
    result = assess_evidence_quality(ResearchReport.model_validate(data))

    review = result["dimensions"]["review_state"]
    assert review["pending_evidence_ids"] == ["evidence-1"]
    assert review["unverified_evidence_ids"] == ["evidence-1"]
    assert result["dimensions"]["uncertainty_and_limitations"]["status"] == "not_documented"
    assert any("pending review" in warning for warning in result["warnings"])
    assert any("does not record uncertainty" in warning for warning in result["warnings"])


def test_quality_flags_rejected_evidence_and_conflicts():
    data = _report()
    data["evidence"][0]["review_state"] = "rejected"
    data["claims"][0]["status"] = "provisional"
    data["conflicts"] = [{
        "claim_a": "claim-1", "claim_b": "claim-2",
        "explanation": "The claims disagree.",
    }]
    result = assess_evidence_quality(ResearchReport.model_validate(data))

    assert result["dimensions"]["review_state"]["status"] == "rejected_evidence_present"
    assert result["dimensions"]["conflicts"]["conflicted_claim_ids"] == ["claim-1", "claim-2"]
    assert any("rejected" in warning for warning in result["warnings"])
    assert any("claim conflicts" in warning for warning in result["warnings"])


def test_quality_requires_validated_report():
    with pytest.raises(TypeError, match="validated ResearchReport"):
        assess_evidence_quality({"not": "a report"})
