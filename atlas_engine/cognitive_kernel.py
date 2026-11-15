"""Deterministic cognitive kernel for THE PROFESSOR.

This control plane turns an incoming task into a bounded, reviewable frame
before model reasoning, specialist routing, memory retrieval, or action proposal.
It performs no network calls, persistence, tool execution, or side effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

MAX_TASK_CHARS = 4_000
MAX_CONTEXT_CHARS = 8_000
MAX_CONSTRAINTS = 24
MAX_QUESTIONS = 8


class CognitiveStage(str, Enum):
    INTAKE = "intake"
    FRAMED = "framed"
    NEEDS_CLARIFICATION = "needs_clarification"
    READY_FOR_REASONING = "ready_for_reasoning"


class ActionBoundary(str, Enum):
    INFORMATION_ONLY = "information_only"
    DRAFT_ONLY = "draft_only"
    HUMAN_APPROVAL_REQUIRED = "human_approval_required"


@dataclass(frozen=True)
class CognitiveRequest:
    task: str
    context: str = ""
    constraints: tuple[str, ...] = ()
    user_goal: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.task, str) or not self.task.strip():
            raise ValueError("A non-empty task is required.")
        if len(self.task) > MAX_TASK_CHARS:
            raise ValueError("Task exceeds the cognitive intake limit.")
        if not isinstance(self.context, str) or len(self.context) > MAX_CONTEXT_CHARS:
            raise ValueError("Context exceeds the cognitive intake limit.")
        if not isinstance(self.constraints, tuple) or len(self.constraints) > MAX_CONSTRAINTS:
            raise ValueError("Constraints must be a bounded tuple.")
        if any(not isinstance(item, str) or not item.strip() or len(item) > 500 for item in self.constraints):
            raise ValueError("Each constraint must be a non-empty string of at most 500 characters.")
        if self.user_goal is not None and (
            not isinstance(self.user_goal, str) or not self.user_goal.strip() or len(self.user_goal) > 1_000
        ):
            raise ValueError("user_goal must be a non-empty string of at most 1,000 characters.")


@dataclass(frozen=True)
class CognitiveFrame:
    stage: CognitiveStage
    task: str
    goal: str
    context: str
    constraints: tuple[str, ...]
    assumptions: tuple[str, ...]
    open_questions: tuple[str, ...]
    action_boundary: ActionBoundary
    reasoning_ready: bool
    review_notes: tuple[str, ...]


_SIDE_EFFECT_TERMS = re.compile(
    r"\b(send|submit|publish|post|buy|purchase|pay|transfer|delete|cancel|book|"
    r"deploy|merge|execute|change|update|create an account|contact them)\b",
    re.IGNORECASE,
)
_DRAFT_TERMS = re.compile(
    r"\b(draft|write|prepare|compose|plan|design|outline)\b", re.IGNORECASE
)


def frame_task(request: CognitiveRequest) -> CognitiveFrame:
    """Build a conservative task frame from information actually supplied."""
    if not isinstance(request, CognitiveRequest):
        raise TypeError("frame_task requires a validated CognitiveRequest.")

    task = request.task.strip()
    context = request.context.strip()
    goal = request.user_goal.strip() if request.user_goal else task
    assumptions: list[str] = []
    questions: list[str] = []
    notes: list[str] = []

    if not context:
        assumptions.append("No additional background context was supplied.")
    if not request.constraints:
        assumptions.append("No explicit constraints were supplied.")
    conversational_greetings = {
        "hi", "hello", "hey", "good morning", "good afternoon",
        "good evening", "thanks", "thank you", "cheers",
    }
    if (
        len(task.split()) <= 2
        and not request.user_goal
        and task.casefold().strip(" !?.") not in conversational_greetings
        and not re.match(
            r"^(explain|describe|summarize|define|compare|analyze|analyse|research|calculate|translate|review|outline)\b",
            task.casefold().strip(),
        )
    ):
        questions.append("What outcome would you like to achieve?")

    if _SIDE_EFFECT_TERMS.search(task):
        boundary = ActionBoundary.HUMAN_APPROVAL_REQUIRED
        notes.append("This may affect an external system or another person; prepare and review before acting.")
    elif _DRAFT_TERMS.search(task):
        boundary = ActionBoundary.DRAFT_ONLY
        notes.append("Produce a draft or proposal only; do not send, publish, or execute it.")
    else:
        boundary = ActionBoundary.INFORMATION_ONLY

    ready = not questions
    stage = CognitiveStage.READY_FOR_REASONING if ready else CognitiveStage.NEEDS_CLARIFICATION
    if not ready:
        notes.append("Clarification is required before detailed planning.")
    else:
        notes.append("Task frame is ready for reasoning; this does not authorize execution.")

    return CognitiveFrame(
        stage=stage,
        task=task,
        goal=goal,
        context=context,
        constraints=tuple(item.strip() for item in request.constraints),
        assumptions=tuple(assumptions),
        open_questions=tuple(questions[:MAX_QUESTIONS]),
        action_boundary=boundary,
        reasoning_ready=ready,
        review_notes=tuple(notes),
    )


def review_frame(frame: CognitiveFrame) -> tuple[str, ...]:
    """Run a deterministic pre-reasoning quality and safety review."""
    if not isinstance(frame, CognitiveFrame):
        raise TypeError("review_frame requires a CognitiveFrame.")
    findings: list[str] = []
    if not frame.task.strip() or not frame.goal.strip():
        findings.append("Task and goal must both be explicit.")
    if frame.open_questions:
        findings.append("Resolve open questions before committing to a detailed plan.")
    if frame.action_boundary is ActionBoundary.HUMAN_APPROVAL_REQUIRED:
        findings.append("Any external action requires separate, verified human approval.")
    if frame.action_boundary is ActionBoundary.DRAFT_ONLY:
        findings.append("Keep output in draft form; do not perform the implied action.")
    if not frame.context:
        findings.append("Reason only from the task and declared constraints; do not imply missing context.")
    return tuple(findings)



@dataclass(frozen=True)
class CognitivePreparation:
    """A framed task plus approved public evidence for a downstream reasoner."""

    frame: CognitiveFrame
    evidence: tuple[dict, ...]
    evidence_context: str
    review_findings: tuple[str, ...]


def prepare_for_reasoning(
    request: CognitiveRequest,
    *,
    retrieve_evidence: bool = True,
    evidence_limit: int = 3,
) -> CognitivePreparation:
    """Compose intake, evidence retrieval and deterministic review.

    Evidence retrieval is restricted by professor_reasoning_context to
    approved, read-only public/curated sources. Evidence excerpts are labelled
    untrusted data by the formatter. Clarification-needed requests do not
    trigger retrieval. This function never calls a model or executes a plan.
    """
    if not isinstance(retrieve_evidence, bool):
        raise ValueError("retrieve_evidence must be a boolean.")
    frame = frame_task(request)
    findings = review_frame(frame)
    if not frame.reasoning_ready or not retrieve_evidence:
        return CognitivePreparation(
            frame=frame,
            evidence=(),
            evidence_context="",
            review_findings=findings,
        )

    from .professor_reasoning_context import (
        build_reasoning_evidence,
        format_evidence_context,
    )

    query_parts = [frame.goal, frame.task, frame.context, *frame.constraints]
    query = " ".join(part for part in query_parts if part)[:MAX_CONTEXT_CHARS]
    evidence = build_reasoning_evidence(query, limit=evidence_limit)
    if not isinstance(evidence, list):
        raise TypeError("Evidence retrieval must return a list.")
    # Preserve provenance fields without allowing arbitrary unbounded payloads.
    bounded_evidence = tuple(
        {
            key: value
            for key, value in item.items()
            if key in {
                "document_id", "source_id", "title", "url",
                "content_sha256", "trust_level", "matched_terms", "excerpt",
            }
        }
        for item in evidence[:3]
        if isinstance(item, dict)
    )
    formatted = format_evidence_context(list(bounded_evidence))
    if not isinstance(formatted, str) or len(formatted) > 3_500:
        raise ValueError("Formatted evidence context exceeded its safety budget.")
    return CognitivePreparation(
        frame=frame,
        evidence=bounded_evidence,
        evidence_context=formatted,
        review_findings=findings,
    )
