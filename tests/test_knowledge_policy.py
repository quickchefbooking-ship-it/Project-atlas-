import json
from datetime import datetime, timezone

import pytest

from atlas_engine import storage
from atlas_engine.knowledge_policy import retrieve_scoped
from atlas_engine.source_division import ingest_document, register_source, review_document


def _isolated_db(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "knowledge-policy.db"))
    storage.init_db()


def _approved(metadata):
    register_source("research", "Research", "research")
    item = ingest_document(
        "research", "Professor learning evidence", "https://example.org/evidence",
        "Professor learning evidence supports safe orchestration and memory.",
        metadata=metadata,
    )
    review_document(item["id"], "approved", "reviewer")
    return item


def test_scoped_retrieval_requires_exact_division_and_excludes_missing_metadata(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    _approved({"division": "engineering"})
    _approved({"division": "wellbeing"})

    results = retrieve_scoped("Professor learning evidence", division="engineering")

    assert len(results) == 1
    assert json.loads(results[0]["metadata_json"])["division"] == "engineering"


def test_scoped_retrieval_requires_jurisdiction_and_population_when_requested(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    _approved({"division": "wellbeing", "jurisdiction": "UK", "population": "adults"})
    _approved({"division": "wellbeing", "jurisdiction": "US", "population": "adults"})

    results = retrieve_scoped(
        "Professor learning evidence",
        division="wellbeing",
        jurisdiction="UK",
        population="adults",
    )

    assert len(results) == 1
    metadata = json.loads(results[0]["metadata_json"])
    assert metadata["jurisdiction"] == "UK"
    assert metadata["population"] == "adults"


def test_freshness_filter_excludes_missing_old_and_future_timestamps(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    _approved({"retrieved_at": "2026-11-12T12:00:00+00:00"})
    _approved({"retrieved_at": "2026-10-01T12:00:00+00:00"})
    _approved({"retrieved_at": "2026-11-15T12:00:00+00:00"})
    _approved({"division": "engineering"})
    now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)

    results = retrieve_scoped(
        "Professor learning evidence", max_age_days=3, as_of=now, limit=10
    )

    assert len(results) == 1
    assert json.loads(results[0]["metadata_json"])["retrieved_at"].startswith("2026-11-12")


def test_expired_documents_are_excluded(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    _approved({"expires_at": "2026-11-12T00:00:00+00:00"})
    _approved({"expires_at": "2026-11-14T00:00:00+00:00"})
    now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)

    results = retrieve_scoped("Professor learning evidence", as_of=now, limit=10)

    assert len(results) == 1
    assert json.loads(results[0]["metadata_json"])["expires_at"].startswith("2026-11-14")


@pytest.mark.parametrize("kwargs", [
    {"max_age_days": -1},
    {"max_age_days": True},
    {"division": ""},
    {"as_of": datetime(2026, 11, 13)},
])
def test_scope_policy_rejects_invalid_policy_inputs(monkeypatch, tmp_path, kwargs):
    _isolated_db(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        retrieve_scoped("Professor learning evidence", **kwargs)
