"""Structured reasoning decomposition and response critique for THE PROFESSOR.

This module validates a reasoner's proposed decomposition and performs a
transparent deterministic pre-delivery review. It does not generate plans,
call models, infer truth, or execute capabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence

from .cognitive_kernel import CognitivePreparation, ActionBoundary

MAX_REASONING_STEPS = 16
MAX_STEP_TEXT = 1_000
MAX_ANSWER_CHARS = 12_000
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "into", "your",
    "you", "are", "was", "were", "will", "would", "could", "should",
    "have", "has", "had", "how", "what", "when", "where", "why", "which",
    "their", "them", "they", "about", "then", "than", "not", "but", "also",
})


class ReasoningValidationError(ValueError):
    """A proposed reasoning decomposition is malformed."""


@dataclass(frozen=True)
class ReasoningStep:
    step_id: str
    objective: str
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.step_id, str) or not self.step_id.strip() or len(self.step_id) > 64:
            raise ReasoningValidationError("Step ID must be non-empty and bounded.")
        if not isinstance(self.objective, str) or not self.objective.strip() or len(self.objective) > MAX_STEP_TEXT:
            raise ReasoningValidationError("Step objective must be non-empty and bounded.")
        if not isinstance(self.depends_on, tuple) or len(self.depends_on) > MAX_REASONING_STEPS:
            raise ReasoningValidationError("Step dependencies must be a bounded tuple.")
        if any(not isinstance(dep, str) or not dep.strip() for dep in self.depends_on):
            raise ReasoningValidationError("Dependency IDs must be non-empty strings.")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ReasoningValidationError("Duplicate dependencies are not allowed.")


@dataclass(frozen=True)
class ReasoningBlueprint:
    goal: str
    steps: tuple[ReasoningStep, ...]
    ordered_step_ids: tuple[str, ...]
    constraints: tuple[str, ...]
    evidence_document_ids: tuple[str, ...]
    action_boundary: ActionBoundary
    execution_enabled: bool = False


@dataclass(frozen=True)
class CritiqueResult:
    accepted_for_delivery: bool
    goal_coverage: float
    constraint_coverage: tuple[tuple[str, bool], ...]
    missing_goal_terms: tuple[str, ...]
    missing_evidence_citations: tuple[str, ...]
    findings: tuple[str, ...]
    method: str = "deterministic_lexical_review"


def _terms(text: str) -> set[str]:
    return {
        term for term in re.findall(r"[a-z0-9]{3,}", text.casefold())
        if term not in _STOPWORDS
    }


def build_reasoning_blueprint(
    preparation: CognitivePreparation,
    steps: Sequence[ReasoningStep],
) -> ReasoningBlueprint:
    """Validate a proposed decomposition against the framed task.

    The decomposition is supplied by a future reasoner; this function only
    validates structure and preserves task boundaries and evidence provenance.
    """
    if not isinstance(preparation, CognitivePreparation):
        raise TypeError("A validated CognitivePreparation is required.")
    if not preparation.frame.reasoning_ready:
        raise ReasoningValidationError("Clarification is required before decomposition.")
    if not isinstance(steps, (tuple, list)) or not 1 <= len(steps) <= MAX_REASONING_STEPS:
        raise ReasoningValidationError("Provide between 1 and 16 reasoning steps.")
    if any(not isinstance(step, ReasoningStep) for step in steps):
        raise TypeError("Every decomposition item must be a ReasoningStep.")
    ids = [step.step_id for step in steps]
    if len(set(ids)) != len(ids):
        raise ReasoningValidationError("Reasoning step IDs must be unique.")
    known = set(ids)
    for step in steps:
        if set(step.depends_on) - known:
            raise ReasoningValidationError("A reasoning step references an unknown dependency.")
        if step.step_id in step.depends_on:
            raise ReasoningValidationError("A reasoning step cannot depend on itself.")

    remaining = {step.step_id: set(step.depends_on) for step in steps}
    ordered: list[str] = []
    while remaining:
        ready = sorted(step_id for step_id, deps in remaining.items() if not deps)
        if not ready:
            raise ReasoningValidationError("Reasoning decomposition contains a dependency cycle.")
        for step_id in ready:
            ordered.append(step_id)
            remaining.pop(step_id)
            for deps in remaining.values():
                deps.discard(step_id)

    evidence_ids = tuple(
        item["document_id"] for item in preparation.evidence
        if isinstance(item.get("document_id"), str) and item["document_id"]
    )
    return ReasoningBlueprint(
        goal=preparation.frame.goal,
        steps=tuple(steps),
        ordered_step_ids=tuple(ordered),
        constraints=preparation.frame.constraints,
        evidence_document_ids=evidence_ids,
        action_boundary=preparation.frame.action_boundary,
        execution_enabled=False,
    )


def critique_answer(
    preparation: CognitivePreparation,
    blueprint: ReasoningBlueprint,
    answer: str,
) -> CritiqueResult:
    """Review goal/constraint coverage and evidence citation presence.

    Lexical coverage is a warning signal, not semantic proof. The result is
    fail-closed for empty answers, missing constraint coverage, missing source
    citations when evidence is attached, or unresolved human approval gates.
    """
    if not isinstance(preparation, CognitivePreparation):
        raise TypeError("A validated CognitivePreparation is required.")
    if not isinstance(blueprint, ReasoningBlueprint):
        raise TypeError("A validated ReasoningBlueprint is required.")
    if not isinstance(answer, str) or not answer.strip() or len(answer) > MAX_ANSWER_CHARS:
        raise ValueError("Answer must contain 1 to 12000 characters.")

    answer_terms = _terms(answer)
    goal_terms = _terms(blueprint.goal)
    missing_goal = tuple(sorted(goal_terms - answer_terms))
    goal_coverage = (
        1.0 if not goal_terms else
        round(len(goal_terms & answer_terms) / len(goal_terms), 3)
    )
    constraints = tuple(
        (constraint, bool(_terms(constraint) & answer_terms))
        for constraint in blueprint.constraints
    )
    missing_citations = tuple(
        doc_id for doc_id in blueprint.evidence_document_ids
        if doc_id not in answer
    )
    findings: list[str] = []
    if goal_coverage < 0.5:
        findings.append("Answer has low lexical coverage of the stated goal; review relevance.")
    if any(not covered for _constraint, covered in constraints):
        findings.append("One or more stated constraints are not visibly addressed.")
    if missing_citations:
        findings.append("Attached evidence document IDs are not cited in the answer.")
    if blueprint.action_boundary is ActionBoundary.HUMAN_APPROVAL_REQUIRED:
        findings.append("External action remains blocked pending separate verified human approval.")
    if blueprint.action_boundary is ActionBoundary.DRAFT_ONLY:
        findings.append("Keep the result as a draft; do not perform the implied action.")
    if not preparation.frame.context:
        findings.append("The answer must not imply access to background context that was not supplied.")

    accepted = (
        goal_coverage >= 0.5
        and all(covered for _constraint, covered in constraints)
        and not missing_citations
        and blueprint.action_boundary is not ActionBoundary.HUMAN_APPROVAL_REQUIRED
    )
    return CritiqueResult(
        accepted_for_delivery=accepted,
        goal_coverage=goal_coverage,
        constraint_coverage=constraints,
        missing_goal_terms=missing_goal,
        missing_evidence_citations=missing_citations,
        findings=tuple(findings),
    )
