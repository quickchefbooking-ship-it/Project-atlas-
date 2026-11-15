import copy

import pytest

from atlas_engine.evidence_engine import build_evidence_bundle
from atlas_engine.evidence_evaluation import evaluate_evidence_bundle
from atlas_engine.professor_report import build_professor_report
from atlas_engine.reviewer_annotations import apply_reviewer_annotations


def empty_bundle():
    return build_evidence_bundle([{
        "title": "Reviewable source",
        "uri": "https://doi.org/10.1000/reviewable",
        "doi": "10.1000/reviewable",
        "publisher": "Example Press",
        "retrieved_at": "2026-11-14T12:00:00Z",
        "claims": [],
    }])


def annotation(relation="supports", **overrides):
    value = {
        "claim_id": "claim-1",
        "text": "The intervention improved the measured outcome.",
        "source_id": "source-1",
        "relation": relation,
    }
    value.update(overrides)
    return value


def test_reviewer_annotations_are_explicit_attributed_and_flow_into_report():
    original = empty_bundle()
    bundle = apply_reviewer_annotations(
        original,
        [annotation()],
        reviewer_id="reviewer-hash-123",
        reviewed_at="2026-11-14T12:30:00Z",
    )
    assert original["claims"] == []
    assert bundle["claims"][0]["annotations"] == [{
        "source_id": "source-1",
        "relation": "supports",
        "reviewer_id": "reviewer-hash-123",
        "reviewed_at": "2026-11-14T12:30:00Z",
    }]

    evaluation = evaluate_evidence_bundle(bundle)
    assessed = evaluation["evaluations"][0]
    assert assessed["status"] == "supported_by_supplied_annotations"
    assert assessed["annotation_audit"] == [{
        "source_id": "source-1",
        "relation": "supports",
        "reviewer_id": "reviewer-hash-123",
        "reviewed_at": "2026-11-14T12:30:00Z",
    }]

    report = build_professor_report(bundle, evaluation)
    assert report["findings"][0]["annotation_audit"] == assessed["annotation_audit"]
    assert report["executive_summary"]["confidence"] == "not_scored"


def test_reviewer_can_add_a_challenge_and_report_shows_disagreement():
    bundle = apply_reviewer_annotations(
        empty_bundle(), [annotation()], reviewer_id="reviewer-a",
        reviewed_at="2026-11-14T12:30:00Z",
    )
    bundle = apply_reviewer_annotations(
        bundle, [annotation("challenges")], reviewer_id="reviewer-b",
        reviewed_at="2026-11-14T12:40:00Z",
    )
    report = build_professor_report(bundle, evaluate_evidence_bundle(bundle))
    assert len(report["disagreements"]) == 1
    assert {item["reviewer_id"] for item in report["disagreements"][0]["annotation_audit"]} == {
        "reviewer-a", "reviewer-b"
    }


@pytest.mark.parametrize("bad", [
    annotation(source_id="source-unknown"),
    annotation(relation="guesses"),
    annotation(extra="not-allowed"),
])
def test_reviewer_annotation_rejects_unknown_source_relation_or_fields(bad):
    with pytest.raises(ValueError):
        apply_reviewer_annotations(
            empty_bundle(), [bad], reviewer_id="reviewer-a",
            reviewed_at="2026-11-14T12:30:00Z",
        )


def test_reviewer_annotation_rejects_duplicate_and_inconsistent_claims():
    bundle = empty_bundle()
    with pytest.raises(ValueError, match="Duplicate reviewer annotation"):
        apply_reviewer_annotations(
            bundle, [annotation(), annotation()],
            reviewer_id="reviewer-a", reviewed_at="2026-11-14T12:30:00Z",
        )
    with pytest.raises(ValueError, match="consistent claim text"):
        apply_reviewer_annotations(
            bundle,
            [annotation(), annotation(text="A different claim", relation="challenges")],
            reviewer_id="reviewer-a", reviewed_at="2026-11-14T12:30:00Z",
        )


def test_reviewer_annotation_requires_bounded_reviewer_attribution():
    with pytest.raises(ValueError, match="reviewer_id"):
        apply_reviewer_annotations(
            empty_bundle(), [annotation()], reviewer_id="",
            reviewed_at="2026-11-14T12:30:00Z",
        )
