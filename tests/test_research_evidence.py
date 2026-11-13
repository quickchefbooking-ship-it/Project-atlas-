import pytest
from pydantic import ValidationError

from atlas_engine.research_evidence import (
    ResearchReport,
    assess_report_integrity,
)


HASH_A = "a" * 64
HASH_B = "b" * 64


def _report():
    return {
        "task_id": "research-task-1",
        "summary": "Two sources describe the same general approach.",
        "recommendation": "Use the approach provisionally and verify implementation details.",
        "claims": [
            {
                "claim_id": "claim-1",
                "statement": "The approach is documented by two reviewed sources.",
                "evidence_ids": ["evidence-1", "evidence-2"],
                "status": "supported",
                "confidence": 0.8,
            },
            {
                "claim_id": "claim-2",
                "statement": "The exact deployment cost is not established.",
                "evidence_ids": ["evidence-1"],
                "status": "unknown",
                "confidence": 0.2,
            },
        ],
        "evidence": [
            {
                "evidence_id": "evidence-1",
                "source_id": "publisher-a",
                "title": "Reviewed source A",
                "uri": "https://example.org/a",
                "content_sha256": HASH_A,
                "trust_level": "reviewed",
                "review_state": "approved",
                "retrieved_at": "2026-11-13T10:00:00Z",
            },
            {
                "evidence_id": "evidence-2",
                "source_id": "publisher-b",
                "title": "Reviewed source B",
                "uri": "https://example.net/b",
                "content_sha256": HASH_B,
                "trust_level": "authoritative",
                "review_state": "approved",
                "retrieved_at": "2026-11-13T10:01:00Z",
            },
        ],
        "uncertainty": ["Deployment costs vary by environment."],
        "limitations": ["This report does not include a live deployment test."],
    }


def test_report_accepts_claims_with_resolvable_approved_evidence():
    report = ResearchReport.model_validate(_report())

    assert report.claims[0].evidence_ids == ["evidence-1", "evidence-2"]
    result = assess_report_integrity(report)
    assert result["distinct_cited_source_count"] == 2
    assert result["truth_assessed"] is False
    assert result["semantic_support_assessed"] is False
    assert result["warnings"] == []


def test_claim_cannot_cite_missing_evidence():
    data = _report()
    data["claims"][0]["evidence_ids"] = ["missing"]

    with pytest.raises(ValidationError, match="resolve to report evidence"):
        ResearchReport.model_validate(data)


def test_supported_claim_requires_approved_reviewed_or_authoritative_source():
    data = _report()
    data["evidence"][0]["trust_level"] = "unverified"
    data["evidence"][0]["review_state"] = "pending"
    data["claims"][0]["evidence_ids"] = ["evidence-1"]

    with pytest.raises(ValidationError, match="supported claim requires"):
        ResearchReport.model_validate(data)


def test_pending_source_can_be_cited_only_as_provisional_or_unknown():
    data = _report()
    data["evidence"][0]["trust_level"] = "unverified"
    data["evidence"][0]["review_state"] = "pending"
    data["claims"][0]["status"] = "provisional"
    data["claims"][0]["evidence_ids"] = ["evidence-1"]

    report = ResearchReport.model_validate(data)
    result = assess_report_integrity(report)

    assert result["pending_or_unverified_evidence_ids"] == ["evidence-1"]
    assert any("pending or unverified" in warning for warning in result["warnings"])


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["claims"].append(d["claims"][0].copy()), "Claim IDs must be unique"),
    (lambda d: d["evidence"].append(d["evidence"][0].copy()), "Evidence IDs must be unique"),
    (lambda d: d["claims"][0].update(evidence_ids=["evidence-1", "evidence-1"]), "same evidence more than once"),
])
def test_duplicate_identifiers_and_citations_are_rejected(mutate, message):
    data = _report()
    mutate(data)

    with pytest.raises(ValidationError, match=message):
        ResearchReport.model_validate(data)


def test_conflict_references_must_point_to_two_existing_claims():
    data = _report()
    data["conflicts"] = [{
        "claim_a": "claim-1",
        "claim_b": "not-a-claim",
        "explanation": "The statements disagree.",
    }]

    with pytest.raises(ValidationError, match="resolve to report claims"):
        ResearchReport.model_validate(data)


def test_conflict_cannot_reference_same_claim_twice():
    data = _report()
    data["conflicts"] = [{
        "claim_a": "claim-1",
        "claim_b": "claim-1",
        "explanation": "Invalid self-conflict.",
    }]

    with pytest.raises(ValidationError, match="cannot conflict with itself"):
        ResearchReport.model_validate(data)


def test_integrity_assessment_warns_when_only_one_source_is_cited():
    data = _report()
    data["claims"][0]["evidence_ids"] = ["evidence-1"]
    data["claims"][1]["evidence_ids"] = ["evidence-1"]
    report = ResearchReport.model_validate(data)

    result = assess_report_integrity(report)

    assert result["distinct_cited_source_count"] == 1
    assert any("Fewer than two distinct sources" in warning for warning in result["warnings"])


def test_report_rejects_unexpected_fields():
    data = _report()
    data["claims"][0]["tool_command"] = "not-allowed"

    with pytest.raises(ValidationError):
        ResearchReport.model_validate(data)
