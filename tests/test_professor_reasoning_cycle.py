import pytest

from atlas_engine.cognitive_kernel import CognitiveRequest, prepare_for_reasoning
from atlas_engine.professor_reasoning_cycle import (
    ReasoningStep, ReasoningValidationError, build_reasoning_blueprint, critique_answer,
)


def prepared(task="Explain the core architecture", constraints=("Use plain language",)):
    return prepare_for_reasoning(
        CognitiveRequest(task=task, context="AtlasOnePro", constraints=constraints),
        retrieve_evidence=False,
    )


def test_decomposition_orders_dependencies_and_never_enables_execution():
    prep = prepared()
    blueprint = build_reasoning_blueprint(prep, (
        ReasoningStep("s2", "Explain how components connect", ("s1",)),
        ReasoningStep("s1", "Identify the core components"),
    ))
    assert blueprint.ordered_step_ids == ("s1", "s2")
    assert blueprint.goal == prep.frame.goal
    assert blueprint.execution_enabled is False


def test_decomposition_rejects_unknown_dependencies_and_cycles():
    prep = prepared()
    with pytest.raises(ReasoningValidationError, match="unknown dependency"):
        build_reasoning_blueprint(prep, (ReasoningStep("a", "Step", ("missing",)),))
    with pytest.raises(ReasoningValidationError, match="cycle"):
        build_reasoning_blueprint(prep, (
            ReasoningStep("a", "First", ("b",)),
            ReasoningStep("b", "Second", ("a",)),
        ))


def test_decomposition_waits_for_clarification():
    prep = prepare_for_reasoning(CognitiveRequest(task="Sort this"), retrieve_evidence=False)
    with pytest.raises(ReasoningValidationError, match="Clarification"):
        build_reasoning_blueprint(prep, (ReasoningStep("a", "Sort"),))


def test_critique_checks_goal_and_constraints_before_delivery():
    prep = prepared(constraints=("Use plain language",))
    blueprint = build_reasoning_blueprint(prep, (ReasoningStep("a", "Describe architecture"),))
    weak = critique_answer(prep, blueprint, "A small answer.")
    assert weak.accepted_for_delivery is False
    assert any("constraints" in finding for finding in weak.findings)
    strong = critique_answer(
        prep, blueprint,
        "The core architecture is explained in plain language, including how the components connect.",
    )
    assert strong.accepted_for_delivery is True


def test_external_action_answer_is_never_marked_approved():
    prep = prepared(task="Send the completed report to the client", constraints=())
    blueprint = build_reasoning_blueprint(prep, (ReasoningStep("a", "Prepare report"),))
    result = critique_answer(prep, blueprint, "The completed report is ready to send.")
    assert result.accepted_for_delivery is False
    assert any("human approval" in finding for finding in result.findings)


def test_evidence_ids_must_be_cited_when_evidence_is_attached():
    from dataclasses import replace
    prep = prepared()
    prep = replace(prep, evidence=({"document_id": "doc-123", "source_id": "source-1"},))
    blueprint = build_reasoning_blueprint(prep, (ReasoningStep("a", "Summarise evidence"),))
    missing = critique_answer(prep, blueprint, "The core architecture has several components.")
    assert missing.accepted_for_delivery is False
    assert missing.missing_evidence_citations == ("doc-123",)
    cited = critique_answer(prep, blueprint, "The core architecture has several components (doc-123).")
    assert cited.missing_evidence_citations == ()
