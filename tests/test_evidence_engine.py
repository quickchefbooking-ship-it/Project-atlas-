import pytest

from atlas_engine.evidence_engine import build_evidence_bundle


def source(title, doi, claims):
    return {
        "title": title,
        "uri": "https://doi.org/" + doi,
        "doi": doi,
        "publisher": "Example Press",
        "retrieved_at": "2026-11-14T12:00:00Z",
        "claims": claims,
    }


def test_bundle_links_claim_annotations_to_sources_and_flags_conflicting_labels():
    bundle = build_evidence_bundle([
        source("Study A", "10.1000/a", [
            {"claim_id": "c1", "text": "Intervention improved outcome", "relation": "supports"},
        ]),
        source("Study B", "10.1000/b", [
            {"claim_id": "c1", "text": "Intervention improved outcome", "relation": "challenges"},
        ]),
    ])
    claim = bundle["claims"][0]
    assert claim["assessment"] == "conflicting_annotations"
    assert claim["annotations"] == [
        {"source_id": "source-1", "relation": "supports"},
        {"source_id": "source-2", "relation": "challenges"},
    ]
    assert bundle["summary"]["confidence"] == "not_scored"
    assert bundle["summary"]["conflicting_claim_count"] == 1


def test_duplicate_doi_is_not_counted_as_independent_corroboration():
    record = source("Same paper", "10.1000/a", [])
    bundle = build_evidence_bundle([record, record])
    assert bundle["summary"]["source_count"] == 2
    assert bundle["summary"]["duplicate_group_count"] == 1
    assert "not independent corroboration" in bundle["duplicate_records"][0]["notice"]


def test_claim_id_cannot_hide_different_claim_text():
    with pytest.raises(ValueError, match="consistent claim text"):
        build_evidence_bundle([
            source("A", "10.1000/a", [{"claim_id": "c1", "text": "Claim one", "relation": "supports"}]),
            source("B", "10.1000/b", [{"claim_id": "c1", "text": "Different claim", "relation": "supports"}]),
        ])


def test_rejects_untrusted_uri_credentials_and_unknown_annotation_fields():
    bad = source("A", "10.1000/a", [])
    bad["uri"] = "https://user:pass@example.org/paper"
    with pytest.raises(ValueError, match="without credentials"):
        build_evidence_bundle([bad])


def test_bundle_rejects_unbounded_input():
    with pytest.raises(ValueError, match="between 1 and 20"):
        build_evidence_bundle([])
