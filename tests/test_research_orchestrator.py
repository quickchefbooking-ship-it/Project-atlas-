import json

import pytest

from atlas_engine import storage
from atlas_engine.model_provider import ProposedCapabilityCall
from atlas_engine.research_capabilities import build_research_registry
from atlas_engine.research_orchestrator import ProfessorResearchOrchestrator
from atlas_engine.research_plan import ResearchPlan


class FakeExecutor:
    def __init__(self, fail_on=None):
        self.registry = build_research_registry()
        self.fail_on = fail_on
        self.calls = []

    def execute(self, proposed: ProposedCapabilityCall, *, granted_scopes: frozenset[str]):
        self.calls.append(proposed.capability_id)
        if proposed.capability_id == self.fail_on:
            raise TimeoutError("private details must not be persisted")
        return {
            "capability_id": proposed.capability_id,
            "capability_version": proposed.capability_version,
            "evidence_state": "approved_existing_knowledge",
            "evidence": [{
                "id": "doc-1",
                "source_id": "library",
                "title": "Verified source",
                "uri": "https://example.org/source",
                "content": "large content must not be copied into run ledger",
                "content_sha256": "a" * 64,
                "trust_level": "reviewed",
            }],
        }


def _setup_db(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "professor-research.db"))
    storage.init_db()


def _plan():
    return ResearchPlan(
        task_id="task-research-001",
        objective="Compare evidence using approved research sources.",
        scope="Only bounded read-only public or approved local sources.",
        success_criteria=["Evidence provenance is recorded", "Each step is auditable"],
        risk_class="low",
        max_duration_seconds=60,
        max_capability_calls=4,
        steps=[
            {
                "step_id": "discover",
                "objective": "Retrieve approved evidence.",
                "capability_id": "source.approved_retrieval",
                "capability_version": "1",
                "arguments": {"query": "research evidence", "limit": 3},
                "rationale": "Use only reviewed knowledge.",
                "expected_evidence": "Document IDs and hashes.",
            },
            {
                "step_id": "compare",
                "objective": "Repeat retrieval for comparison.",
                "capability_id": "source.approved_retrieval",
                "capability_version": "1",
                "arguments": {"query": "independent evidence", "limit": 2},
                "rationale": "Check evidence coverage.",
                "expected_evidence": "Second set of document references.",
                "depends_on": ["discover"],
            },
        ],
    )


def test_orchestrator_executes_plan_and_persists_replayable_audit(monkeypatch, tmp_path):
    _setup_db(monkeypatch, tmp_path)
    executor = FakeExecutor()
    orchestrator = ProfessorResearchOrchestrator(executor)

    result = orchestrator.run(
        _plan(),
        granted_scopes=frozenset({"knowledge.approved.read"}),
    )

    assert result["status"] == "completed"
    assert executor.calls == ["source.approved_retrieval", "source.approved_retrieval"]
    saved = orchestrator.get_run(result["run_id"])
    assert saved["status"] == "completed"
    assert saved["plan"]["task_id"] == "task-research-001"
    assert [step["status"] for step in saved["steps"]] == ["completed", "completed"]
    evidence = saved["steps"][0]["result"]["evidence"][0]
    assert evidence["document_id"] == "doc-1"
    assert evidence["content_sha256"] == "a" * 64
    assert "content" not in evidence


def test_orchestrator_stops_after_failure_and_marks_remaining_steps_skipped(monkeypatch, tmp_path):
    _setup_db(monkeypatch, tmp_path)
    executor = FakeExecutor(fail_on="source.approved_retrieval")
    orchestrator = ProfessorResearchOrchestrator(executor)

    result = orchestrator.run(
        _plan(),
        granted_scopes=frozenset({"knowledge.approved.read"}),
    )

    assert result["status"] == "failed"
    assert result["failed_step"] == "discover"
    assert result["error_type"] == "TimeoutError"
    assert executor.calls == ["source.approved_retrieval"]
    saved = orchestrator.get_run(result["run_id"])
    assert [step["status"] for step in saved["steps"]] == ["failed", "skipped"]
    serialized = json.dumps(saved)
    assert "private details" not in serialized


def test_orchestrator_validates_entire_plan_before_executing_any_step(monkeypatch, tmp_path):
    _setup_db(monkeypatch, tmp_path)
    executor = FakeExecutor()
    orchestrator = ProfessorResearchOrchestrator(executor)
    plan = _plan()
    invalid_steps = [step.model_dump() for step in plan.steps]
    invalid_steps[1]["capability_id"] = "shell.exec"
    invalid_steps[1]["capability_version"] = "1"
    invalid_plan = ResearchPlan(
        **{**plan.model_dump(), "steps": invalid_steps}
    )

    with pytest.raises(ValueError, match="not registered"):
        orchestrator.run(
            invalid_plan,
            granted_scopes=frozenset({"knowledge.approved.read"}),
        )
    assert executor.calls == []


def test_orchestrator_rejects_mutable_scopes_and_unvalidated_plan(monkeypatch, tmp_path):
    _setup_db(monkeypatch, tmp_path)
    orchestrator = ProfessorResearchOrchestrator(FakeExecutor())

    with pytest.raises(TypeError, match="immutable capability scopes"):
        orchestrator.run(_plan(), granted_scopes={"knowledge.approved.read"})
    with pytest.raises(TypeError, match="validated ResearchPlan"):
        orchestrator.run(_plan().model_dump(), granted_scopes=frozenset({"knowledge.approved.read"}))
