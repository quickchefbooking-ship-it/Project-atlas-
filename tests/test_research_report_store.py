import pytest

from atlas_engine import storage
from atlas_engine.model_provider import ProposedCapabilityCall
from atlas_engine.research_capabilities import build_research_registry
from atlas_engine.research_orchestrator import ProfessorResearchOrchestrator
from atlas_engine.research_plan import ResearchPlan
from atlas_engine.research_report_store import get_research_report, save_research_report
from atlas_engine.research_evidence import ResearchReport


class EvidenceExecutor:
    def __init__(self):
        self.registry = build_research_registry()

    def execute(self, proposed: ProposedCapabilityCall, *, granted_scopes: frozenset[str]):
        return {
            "capability_id": proposed.capability_id,
            "capability_version": proposed.capability_version,
            "evidence": [{
                "document_id": "doc-run-1", "source_id": "approved-library",
                "title": "Reviewed source", "uri": "https://example.org/research",
                "content_sha256": "a" * 64, "trust_level": "reviewed",
                "review_state": "approved",
            }],
        }


def _setup_db(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "report-store.db"))
    storage.init_db()


def _run(orchestrator):
    plan = ResearchPlan(
        task_id="task-report-1", objective="Collect reviewed evidence.",
        scope="Approved knowledge only.", success_criteria=["Evidence is traceable."],
        risk_class="low", max_duration_seconds=30, max_capability_calls=1,
        steps=[{
            "step_id": "retrieve", "objective": "Retrieve reviewed evidence.",
            "capability_id": "source.approved_retrieval", "capability_version": "1",
            "arguments": {"query": "research", "limit": 1},
            "rationale": "Use approved knowledge.", "expected_evidence": "Document ID and digest.",
        }],
    )
    return orchestrator.run(plan, granted_scopes=frozenset({"knowledge.approved.read"}))


def _report():
    return ResearchReport.model_validate({
        "task_id": "task-report-1", "summary": "The source records the topic.",
        "recommendation": "Use it as a starting point.",
        "claims": [{
            "claim_id": "claim-1", "statement": "A reviewed source was retrieved.",
            "evidence_ids": ["doc-run-1"], "status": "supported", "confidence": 0.7,
        }],
        "evidence": [{
            "evidence_id": "doc-run-1", "source_id": "approved-library",
            "title": "Reviewed source", "uri": "https://example.org/research",
            "content_sha256": "a" * 64, "trust_level": "reviewed",
            "review_state": "approved", "retrieved_at": "2026-11-13T10:00:00Z",
        }],
        "uncertainty": ["The source does not establish every detail."],
        "limitations": ["Only one source was retrieved."],
    })


def test_report_is_bound_to_completed_run_and_retrievable(monkeypatch, tmp_path):
    _setup_db(monkeypatch, tmp_path)
    orchestrator = ProfessorResearchOrchestrator(EvidenceExecutor())
    run = _run(orchestrator)
    saved = save_research_report(run["run_id"], _report())
    loaded = get_research_report(run["run_id"])
    assert saved["task_id"] == "task-report-1"
    assert loaded["report"]["claims"][0]["evidence_ids"] == ["doc-run-1"]
    assert loaded["integrity"]["truth_assessed"] is False


@pytest.mark.parametrize("field,value", [
    ("source_id", "forged-source"), ("content_sha256", "b" * 64),
    ("trust_level", "authoritative"), ("review_state", "pending"),
    ("uri", "https://attacker.example/forged"),
])
def test_report_cannot_forge_evidence_metadata(monkeypatch, tmp_path, field, value):
    _setup_db(monkeypatch, tmp_path)
    orchestrator = ProfessorResearchOrchestrator(EvidenceExecutor())
    run = _run(orchestrator)
    data = _report().model_dump()
    data["evidence"][0][field] = value
    if field == "review_state":
        data["claims"][0]["status"] = "provisional"
    with pytest.raises(ValueError, match="does not match the run ledger"):
        save_research_report(run["run_id"], ResearchReport.model_validate(data))


def test_report_cannot_use_evidence_from_another_run(monkeypatch, tmp_path):
    _setup_db(monkeypatch, tmp_path)
    orchestrator = ProfessorResearchOrchestrator(EvidenceExecutor())
    run = _run(orchestrator)
    data = _report().model_dump()
    data["evidence"][0]["evidence_id"] = "other-run-document"
    data["claims"][0]["evidence_ids"] = ["other-run-document"]
    with pytest.raises(ValueError, match="must come from this run"):
        save_research_report(run["run_id"], ResearchReport.model_validate(data))


def test_report_task_id_must_match_run(monkeypatch, tmp_path):
    _setup_db(monkeypatch, tmp_path)
    orchestrator = ProfessorResearchOrchestrator(EvidenceExecutor())
    run = _run(orchestrator)
    data = _report().model_dump()
    data["task_id"] = "different-task"
    with pytest.raises(ValueError, match="task ID does not match"):
        save_research_report(run["run_id"], ResearchReport.model_validate(data))


def test_duplicate_report_write_is_rejected(monkeypatch, tmp_path):
    _setup_db(monkeypatch, tmp_path)
    orchestrator = ProfessorResearchOrchestrator(EvidenceExecutor())
    run = _run(orchestrator)
    report = _report()
    save_research_report(run["run_id"], report)
    with pytest.raises(Exception):
        save_research_report(run["run_id"], report)
    assert get_research_report(run["run_id"]) is not None
