import pytest

from atlas_engine.evidence_engine import build_evidence_bundle
from atlas_engine.evidence_evaluation import evaluate_evidence_bundle


def make_source(title, doi, claims):
    return {
        "title": title,
        "uri": "https://doi.org/" + doi,
        "doi": doi,
        "publisher": "Example Press",
        "retrieved_at": "2026-11-14T12:00:00Z",
        "claims": claims,
    }


def test_evaluation_distinguishes_support_challenge_conflict_and_insufficient():
    bundle = build_evidence_bundle([
        make_source("A", "10.1000/a", [
            {"claim_id": "supported", "text": "Claim A", "relation": "supports"},
            {"claim_id": "conflict", "text": "Claim B", "relation": "supports"},
        ]),
        make_source("B", "10.1000/b", [
            {"claim_id": "challenged", "text": "Claim C", "relation": "challenges"},
            {"claim_id": "conflict", "text": "Claim B", "relation": "challenges"},
            {"claim_id": "mentioned", "text": "Claim D", "relation": "mentions"},
        ]),
    ])
    result = evaluate_evidence_bundle(bundle)
    by_id = {item["claim_id"]: item for item in result["evaluations"]}
    assert by_id["supported"]["status"] == "supported_by_supplied_annotations"
    assert by_id["challenged"]["status"] == "challenged_by_supplied_annotations"
    assert by_id["conflict"]["status"] == "conflicting_annotations"
    assert by_id["mentioned"]["status"] == "insufficient_evidence"
    assert all(item["confidence"] == "not_scored" for item in result["evaluations"])
    assert result["summary"]["claim_count"] == 4


def test_duplicate_records_count_as_one_record_group_not_independent_support():
    record = make_source("Same record", "10.1000/same", [
        {"claim_id": "c1", "text": "Claim", "relation": "supports"},
    ])
    bundle = build_evidence_bundle([record, record])
    result = evaluate_evidence_bundle(bundle)
    evaluation = result["evaluations"][0]
    assert evaluation["annotated_source_count"] == 2
    assert evaluation["distinct_record_group_count"] == 1
    assert result["summary"]["duplicate_groups_treated_as_single_record_groups"] == 1


def test_evaluation_rejects_annotations_that_reference_unknown_sources():
    bundle = build_evidence_bundle([
        make_source("A", "10.1000/a", [
            {"claim_id": "c1", "text": "Claim", "relation": "supports"},
        ]),
    ])
    bundle["claims"][0]["annotations"][0]["source_id"] = "source-999"
    with pytest.raises(ValueError, match="unknown source"):
        evaluate_evidence_bundle(bundle)


def test_evaluation_rejects_unknown_bundle_version():
    with pytest.raises(ValueError, match="schema version 1"):
        evaluate_evidence_bundle({"schema_version": 2, "sources": [], "claims": [], "duplicate_records": []})
