"""Characterize factual correctness gaps in lexical-only answer critique.

These are synthetic tests. They do not change runtime behavior or claim that
lexical coverage is a correctness verifier.
"""
from atlas_engine.cognitive_kernel import CognitiveRequest, prepare_for_reasoning
from atlas_engine.professor_reasoning_cycle import (
    ReasoningStep, build_reasoning_blueprint, critique_answer,
)


def _prepared(task: str, constraints: tuple[str, ...] = ()):
    return prepare_for_reasoning(
        CognitiveRequest(task=task, context="Synthetic evaluation fixture", constraints=constraints),
        retrieve_evidence=False,
    )


def test_keyword_rich_factually_wrong_answer_is_accepted_by_lexical_critique():
    """A deliberately wrong answer can satisfy visible keyword coverage."""
    prep = _prepared("Explain the core architecture", ("Use plain language",))
    blueprint = build_reasoning_blueprint(
        prep, (ReasoningStep("s1", "Explain core components"),)
    )

    expected_facts = ("architecture has multiple components",)
    answer = (
        "The core architecture is explained in plain language. "
        "It consists of exactly zero components and has no connections."
    )

    # Independent fixture label: this answer contradicts the expected fact.
    assert expected_facts[0] not in answer
    assert "zero components" in answer

    # Characterize the known gap: current critique only checks lexical overlap.
    critique = critique_answer(prep, blueprint, answer)
    assert critique.accepted_for_delivery is True


def test_synthetic_answer_with_missing_expected_fact_is_not_semantically_checked():
    """Expected-fact labels are deliberately independent of critique output."""
    prep = _prepared("Explain the core architecture", ("Use plain language",))
    blueprint = build_reasoning_blueprint(
        prep, (ReasoningStep("s1", "Explain core components"),)
    )
    expected_facts = ("architecture has multiple components",)
    answer = "The core architecture is explained in plain language."

    assert expected_facts[0] not in answer
    critique = critique_answer(prep, blueprint, answer)
    assert critique.accepted_for_delivery is True
