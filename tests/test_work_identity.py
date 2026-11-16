import pytest

from atlas_engine.work_identity import (
    detect_duplicate_work_groups,
    normalize_canonical_uri,
    normalize_doi,
    normalize_provider_identifiers,
)


def test_doi_normalization_handles_resolver_and_doi_prefix_forms():
    assert normalize_doi("https://doi.org/10.1234/ABC.X") == "10.1234/abc.x"
    assert normalize_doi("doi:10.1234/ABC.X") == "10.1234/abc.x"
    assert normalize_doi("10.1234/ABC.X") == "10.1234/abc.x"


def test_canonical_uri_normalization_preserves_query_but_normalizes_host_and_default_port():
    assert normalize_canonical_uri("HTTPS://Example.ORG:443/Paper/") == "https://example.org/Paper"
    assert normalize_canonical_uri("https://example.org/paper?version=2") == "https://example.org/paper?version=2"


@pytest.mark.parametrize("uri", [
    "ftp://example.org/paper",
    "https://user:password@example.org/paper",
    "https://example.org:8443/paper",
    "https://example.org:80/paper",
    "http://example.org:443/paper",
    "https://example.org/paper#section",
])
def test_canonical_uri_rejects_unsafe_or_ambiguous_uri_forms(uri):
    with pytest.raises(ValueError):
        normalize_canonical_uri(uri)


def test_provider_identifier_namespaces_are_allowlisted_and_bounded():
    assert normalize_provider_identifiers({"pmid": "123"}) == {"pmid": "123"}
    with pytest.raises(ValueError, match="namespace"):
        normalize_provider_identifiers({"unknown_provider": "123"})


def test_same_doi_and_alias_uri_are_grouped_even_with_different_resolver_forms():
    result = detect_duplicate_work_groups([
        {"doi": "10.1000/abc", "uri": "https://doi.org/10.1000/abc"},
        {"doi": "https://doi.org/10.1000/ABC", "uri": "https://publisher.example/article/1"},
    ])
    assert result["duplicate_groups"][0]["source_indices"] == [0, 1]
    assert "doi:10.1000/abc" in result["duplicate_groups"][0]["identifier_aliases"]


def test_provider_identifier_groups_records_when_one_record_lacks_doi():
    result = detect_duplicate_work_groups([
        {"uri": "https://publisher.example/a", "identifiers": {"pubmed": "12345"}},
        {"uri": "https://publisher.example/b", "identifiers": {"pubmed": "12345"}},
    ])
    assert result["duplicate_groups"][0]["source_indices"] == [0, 1]


def test_conflicting_dois_prevent_provider_or_uri_alias_from_merging_records():
    result = detect_duplicate_work_groups([
        {"doi": "10.1000/first", "uri": "https://publisher.example/shared", "identifiers": {"crossref": "same-id"}},
        {"doi": "10.1000/second", "uri": "https://publisher.example/shared", "identifiers": {"crossref": "same-id"}},
    ])
    assert result["duplicate_groups"] == []
    assert len(result["identifier_conflicts"]) == 2
    assert all(item["status"] == "conflicting_identifiers_not_merged" for item in result["identifier_conflicts"])


def test_transitive_aliases_form_one_record_group_without_doi_conflict():
    result = detect_duplicate_work_groups([
        {"doi": "10.1000/work", "uri": "https://doi.org/10.1000/work"},
        {"uri": "https://publisher.example/record", "identifiers": {"openalex": "W123"}},
        {"uri": "https://publisher.example/other", "identifiers": {"openalex": "W123"}, "doi": "10.1000/work"},
    ])
    assert result["duplicate_groups"][0]["source_indices"] == [0, 1, 2]



def test_doi_suffix_punctuation_is_not_silently_rewritten():
    assert normalize_doi("10.1234/example.") == "10.1234/example."
