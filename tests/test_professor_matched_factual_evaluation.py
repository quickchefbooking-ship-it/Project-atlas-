"""Matched synthetic factual-evaluation suite against lexical critique.

Labels are fixture-owned exact assertions/contradictions, independent from
critique_answer. This is characterization, not a general semantic verifier.
"""
from dataclasses import replace

from atlas_engine.cognitive_kernel import CognitiveRequest, prepare_for_reasoning
from atlas_engine.professor_reasoning_cycle import (
    ReasoningStep, build_reasoning_blueprint, critique_answer,
)


CASES = (
    {
        "name": "correct_expected_fact",
        "answer": "The synthetic service architecture has three layers, described in plain language.",
        "required": ("three layers",),
        "forbidden": ("zero layers",),
        "expected_correct": True,
        "expected_critique_accept": True,
    },
    {
        "name": "contradictory_fact_with_keyword_overlap",
        "answer": "The synthetic service architecture has zero layers, described in plain language.",
        "required": ("three layers",),
        "forbidden": ("zero layers",),
        "expected_correct": False,
        "expected_critique_accept": True,
    },
    {
        "name": "omitted_expected_fact",
        "answer": "The synthetic service architecture is described in plain language.",
        "required": ("three layers",),
        "forbidden": (),
        "expected_correct": False,
        "expected_critique_accept": True,
    },
    {
        "name": "constraint_missing",
        "answer": "The synthetic service architecture has three layers.",
        "required": ("three layers",),
        "forbidden": (),
        "expected_correct": True,
        "expected_critique_accept": False,
    },
)


def _fixture_label(case):
    answer = case["answer"].casefold()
    return all(term.casefold() in answer for term in case["required"]) and not any(
        term.casefold() in answer for term in case["forbidden"]
    )


def test_matched_synthetic_factual_suite_characterizes_baseline():
    prep = prepare_for_reasoning(
        CognitiveRequest(
            task="Describe the synthetic service architecture",
            context="Fixture-only system",
            constraints=("Use plain language",),
        ),
        retrieve_evidence=False,
    )
    blueprint = build_reasoning_blueprint(
        prep, (ReasoningStep("s1", "Describe architecture facts"),)
    )

    outcomes = []
    for case in CASES:
        label = _fixture_label(case)
        critique = critique_answer(prep, blueprint, case["answer"])
        outcomes.append((case["name"], label, critique.accepted_for_delivery))
        assert label is case["expected_correct"]
        assert critique.accepted_for_delivery is case["expected_critique_accept"]

    true_accepts = sum(label and accepted for _, label, accepted in outcomes)
    false_accepts = sum((not label) and accepted for _, label, accepted in outcomes)
    false_rejects = sum(label and (not accepted) for _, label, accepted in outcomes)
    total = len(outcomes)

    assert true_accepts == 1
    assert false_accepts == 2
    assert false_rejects == 1
    assert total == 4
    assert false_accepts / total == 0.5
    assert false_rejects / total == 0.25


def test_matched_suite_citation_presence_is_not_source_truth():
    prep = prepare_for_reasoning(
        CognitiveRequest(
            task="Summarise synthetic evidence about architecture",
            context="Fixture-only system",
            constraints=("Use plain language",),
        ),
        retrieve_evidence=False,
    )
    prep = replace(prep, evidence=({"document_id": "fixture-doc-1"},))
    blueprint = build_reasoning_blueprint(
        prep, (ReasoningStep("s1", "Summarise evidence"),)
    )
    answer = (
        "The synthetic architecture has three layers in plain language "
        "(fixture-doc-1), but the citation text is not checked against source contents."
    )
    critique = critique_answer(prep, blueprint, answer)
    assert critique.accepted_for_delivery is True
    assert "fixture-doc-1" not in critique.missing_evidence_citations
