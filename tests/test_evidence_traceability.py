import hashlib

import pytest

from atlas_engine.evidence_traceability import verify_evidence_excerpt


SOURCE = (
    "Title: Example public report\n"
    "Section 2.1\n"
    "The intervention was associated with a lower observed rate in this sample.\n"
    "Limitations: the study was observational.\n"
)


def _verify(**overrides):
    values = {
        "source_uri": "https://example.org/research/report",
        "source_text": SOURCE,
        "excerpt": "The intervention was associated with a lower observed rate in this sample.",
        "locator": "Section 2.1, paragraph 1",
        "claim_id": "claim-1",
        "claim_text": "The intervention was associated with a lower observed rate.",
        "relation": "supports",
        "reviewer_id": "reviewer-7",
        "reviewed_at": "2026-11-15T20:00:00Z",
    }
    values.update(overrides)
    return verify_evidence_excerpt(**values)


def test_exact_excerpt_is_bound_to_source_snapshot_and_reviewer():
    result = _verify()
    expected_digest = hashlib.sha256(SOURCE.encode("utf-8")).hexdigest()
    assert result["traceability_status"] == "exact_excerpt_found"
    assert result["source_sha256"] == expected_digest
    assert result["review_status"] == "reviewer_attributed"
    assert result["reviewer_id"] == "reviewer-7"
    assert result["claim_support_assessment"] == "not_machine_assessed"
    assert result["source_credibility_assessment"] == "not_assessed"


def test_excerpt_not_present_in_snapshot_is_not_traceable():
    result = _verify(excerpt="This wording does not occur in the source.")
    assert result["traceability_status"] == "excerpt_not_found"


def test_changed_source_snapshot_fails_expected_digest_check():
    result = _verify(
        source_text=SOURCE + "A later correction was published.\n",
        expected_source_sha256=hashlib.sha256(SOURCE.encode("utf-8")).hexdigest(),
    )
    assert result["traceability_status"] == "source_version_mismatch"


def test_matching_expected_digest_is_accepted():
    result = _verify(expected_source_sha256=hashlib.sha256(SOURCE.encode("utf-8")).hexdigest())
    assert result["traceability_status"] == "exact_excerpt_found"


def test_reviewer_attribution_is_optional_but_cannot_be_partial():
    result = _verify(reviewer_id=None, reviewed_at=None)
    assert result["review_status"] == "unreviewed"
    assert result["reviewer_id"] is None
    with pytest.raises(ValueError, match="supplied together"):
        _verify(reviewer_id="reviewer-7", reviewed_at=None)


@pytest.mark.parametrize(
    "uri",
    [
        "http://example.org/report",
        "https://user:pass@example.org/report",
        "https://example.org:8443/report",
        "file:///etc/passwd",
        "https://",
    ],
)
def test_source_uri_must_be_absolute_https_without_credentials_or_alternate_ports(uri):
    with pytest.raises(ValueError):
        _verify(source_uri=uri)


@pytest.mark.parametrize("relation", ["agree", "true", "probably", None, []])
def test_relation_must_be_one_of_explicit_reviewer_labels(relation):
    with pytest.raises(ValueError):
        _verify(relation=relation)


def test_reviewer_timestamp_must_be_timezone_aware():
    with pytest.raises(ValueError, match="include a timezone"):
        _verify(reviewed_at="2026-11-15T20:00:00")


def test_oversized_source_and_excerpt_are_rejected():
    with pytest.raises(ValueError, match="1 MB character limit"):
        _verify(source_text="x" * 1_000_001)
    with pytest.raises(ValueError, match="2,000 characters"):
        _verify(excerpt="x" * 2_001)


def test_invalid_expected_digest_is_rejected():
    with pytest.raises(ValueError, match="64-character SHA-256"):
        _verify(expected_source_sha256="not-a-digest")


def test_locator_is_retained_but_not_claimed_as_machine_verified():
    result = _verify(locator="Page 14, table 2")
    assert result["locator"] == "Page 14, table 2"
    assert any("not independently resolved" in item for item in result["limitations"])
