import pytest

from atlas_engine import storage
from atlas_engine.model_provider import ProposedCapabilityCall
from atlas_engine.public_research_adapters import SourceDocument
from atlas_engine.research_capability_executor import ResearchCapabilityExecutor
from atlas_engine.source_division import register_source


def _isolated_db(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "research-executor.db"))
    storage.init_db()


def test_executor_stages_external_results_as_pending_unverified(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    register_source("crossref-public", "Crossref", "crossref_public_api")

    def fake_crossref(query, limit=5):
        assert query == "AI research agents"
        assert limit == 2
        return [
            SourceDocument(
                title="Research agents study",
                uri="https://doi.org/10.1234/example",
                content="A public bibliographic record.",
                metadata={"publisher": "Example Publisher", "retrieved_at": "2026-11-13"},
            )
        ]

    executor = ResearchCapabilityExecutor(
        adapter_functions={"crossref.search": fake_crossref}
    )
    result = executor.execute(
        ProposedCapabilityCall(
            capability_id="crossref.search",
            capability_version="1",
            arguments={"query": "AI research agents", "limit": 2},
        ),
        granted_scopes=frozenset({"public.research.read"}),
    )

    assert result["evidence_state"] == "pending_unverified_external_source"
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["review_state"] == "pending"
    assert result["evidence"][0]["trust_level"] == "unverified"
    assert result["evidence"][0]["content_sha256"]
    assert storage.list_source_documents(state="pending", limit=10)


def test_executor_refuses_missing_scope_before_adapter_call(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    called = []

    def fake_crossref(*_args, **_kwargs):
        called.append(True)
        return []

    executor = ResearchCapabilityExecutor(
        adapter_functions={"crossref.search": fake_crossref}
    )
    with pytest.raises(PermissionError, match="required research capability scope"):
        executor.execute(
            ProposedCapabilityCall(
                capability_id="crossref.search",
                capability_version="1",
                arguments={"query": "AI research agents"},
            ),
            granted_scopes=frozenset(),
        )
    assert called == []


def test_executor_reads_only_approved_local_knowledge():
    executor = ResearchCapabilityExecutor(
        source_retriever=lambda query, limit=5: [{"query": query, "limit": limit, "trust_level": "reviewed"}]
    )
    result = executor.execute(
        ProposedCapabilityCall(
            capability_id="source.approved_retrieval",
            capability_version="1",
            arguments={"query": "approved research", "limit": 3},
        ),
        granted_scopes=frozenset({"knowledge.approved.read"}),
    )
    assert result["evidence_state"] == "approved_existing_knowledge"
    assert result["evidence"] == [
        {"query": "approved research", "limit": 3, "trust_level": "reviewed"}
    ]


def test_executor_rejects_mutable_or_invalid_scope_container():
    executor = ResearchCapabilityExecutor()
    with pytest.raises(TypeError, match="immutable capability scopes"):
        executor.execute(
            ProposedCapabilityCall(
                capability_id="source.approved_retrieval",
                capability_version="1",
                arguments={"query": "approved research"},
            ),
            granted_scopes={"knowledge.approved.read"},
        )
