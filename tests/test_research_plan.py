import pytest
from pydantic import ValidationError

from atlas_engine.research_plan import ResearchPlan


def _plan(**overrides):
    values = {
        "task_id": "research-001",
        "objective": "Compare reliable evidence about a bounded technical question.",
        "scope": "Public sources only; compare primary documentation and independent research.",
        "success_criteria": ["At least two independent sources", "Claims trace to evidence"],
        "risk_class": "low",
        "max_duration_seconds": 120,
        "max_capability_calls": 4,
        "steps": [
            {
                "step_id": "discover",
                "objective": "Find relevant source records.",
                "capability_id": "crossref.search",
                "rationale": "Identify scholarly literature.",
                "expected_evidence": "Bibliographic records and source URLs.",
            },
            {
                "step_id": "compare",
                "objective": "Compare findings and source provenance.",
                "capability_id": "source.approved_retrieval",
                "rationale": "Check claims against approved records.",
                "expected_evidence": "Evidence records with hashes and retrieval dates.",
                "depends_on": ["discover"],
            },
        ],
    }
    values.update(overrides)
    return ResearchPlan(**values)


def test_research_plan_accepts_bounded_versioned_plan():
    plan = _plan()
    assert plan.schema_version == "1.0"
    assert len(plan.steps) == 2
    assert plan.steps[1].depends_on == ["discover"]


def test_research_plan_rejects_unregistered_or_executable_fields():
    with pytest.raises(ValidationError):
        _plan(unrestricted_browser=True)
    with pytest.raises(ValidationError):
        _plan(steps=[{
            "step_id": "run",
            "objective": "Execute code.",
            "capability_id": "shell.exec",
            "rationale": "Run arbitrary code.",
            "expected_evidence": "Process output.",
            "command": "curl example.org",
        }])


def test_research_plan_rejects_high_risk_and_excessive_budgets():
    with pytest.raises(ValidationError):
        _plan(risk_class="high")
    with pytest.raises(ValidationError):
        _plan(max_duration_seconds=601)
    with pytest.raises(ValidationError):
        _plan(max_capability_calls=21)


def test_research_plan_rejects_duplicate_steps_and_missing_dependencies():
    steps = [
        {
            "step_id": "same",
            "objective": "Find evidence.",
            "capability_id": "crossref.search",
            "rationale": "Search papers.",
            "expected_evidence": "Source records.",
        },
        {
            "step_id": "same",
            "objective": "Compare evidence.",
            "capability_id": "source.approved_retrieval",
            "rationale": "Verify records.",
            "expected_evidence": "Citations.",
        },
    ]
    with pytest.raises(ValidationError):
        _plan(steps=steps)

    with pytest.raises(ValidationError):
        _plan(steps=[{
            "step_id": "one",
            "objective": "Find evidence.",
            "capability_id": "crossref.search",
            "rationale": "Search papers.",
            "expected_evidence": "Source records.",
            "depends_on": ["missing"],
        }])


def test_research_plan_rejects_dependency_cycles():
    steps = [
        {
            "step_id": "one",
            "objective": "First step.",
            "capability_id": "crossref.search",
            "rationale": "Discover.",
            "expected_evidence": "Sources.",
            "depends_on": ["two"],
        },
        {
            "step_id": "two",
            "objective": "Second step.",
            "capability_id": "source.approved_retrieval",
            "rationale": "Verify.",
            "expected_evidence": "Evidence.",
            "depends_on": ["one"],
        },
    ]
    with pytest.raises(ValidationError, match="dependency cycle"):
        _plan(steps=steps)
