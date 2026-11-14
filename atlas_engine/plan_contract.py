"""Typed, bounded planning contract for Professor's orchestration core.

Plans describe work; they do not execute commands or grant capabilities.
External side effects remain blocked until a separate, action-bound approval
and an authorized capability executor are supplied by the application.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


MAX_PLAN_STEPS = 64
MAX_PLAN_TEXT = 2_000
MAX_DEPENDENCIES_PER_STEP = 16


class PlanValidationError(ValueError):
    """A Professor plan is malformed or violates orchestration policy."""


class RiskClass(str, Enum):
    READ_ONLY = "read_only"
    LOCAL_COMPUTATION = "local_computation"
    DRAFT_CREATION = "draft_creation"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    PRIVILEGED = "privileged"


class PlanState(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    capability: str
    objective: str
    risk: RiskClass
    depends_on: tuple[str, ...] = ()
    required_scopes: tuple[str, ...] = ()
    expected_output: str = ""
    timeout_seconds: int = 30
    resource_budget: int = 1

    def __post_init__(self) -> None:
        for value, label in (
            (self.step_id, "step_id"),
            (self.capability, "capability"),
            (self.objective, "objective"),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > MAX_PLAN_TEXT:
                raise PlanValidationError(f"{label} must be a non-empty bounded string.")
        if not isinstance(self.risk, RiskClass):
            raise PlanValidationError("risk must be a recognized RiskClass.")
        if not isinstance(self.depends_on, tuple) or len(self.depends_on) > MAX_DEPENDENCIES_PER_STEP:
            raise PlanValidationError("depends_on must be a bounded tuple.")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise PlanValidationError("A step cannot repeat a dependency.")
        if any(not isinstance(item, str) or not item.strip() for item in self.depends_on):
            raise PlanValidationError("Dependency identifiers must be non-empty strings.")
        if not isinstance(self.required_scopes, tuple) or any(
            not isinstance(scope, str) or not scope.strip() for scope in self.required_scopes
        ):
            raise PlanValidationError("required_scopes must be a tuple of non-empty strings.")
        if len(set(self.required_scopes)) != len(self.required_scopes):
            raise PlanValidationError("Required scopes cannot contain duplicates.")
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, int) or not 1 <= self.timeout_seconds <= 900:
            raise PlanValidationError("timeout_seconds must be between 1 and 900.")
        if isinstance(self.resource_budget, bool) or not isinstance(self.resource_budget, int) or not 1 <= self.resource_budget <= 100:
            raise PlanValidationError("resource_budget must be between 1 and 100.")
        if not isinstance(self.expected_output, str) or len(self.expected_output) > MAX_PLAN_TEXT:
            raise PlanValidationError("expected_output must be a bounded string.")


@dataclass(frozen=True)
class ProfessorPlan:
    plan_id: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    steps: tuple[PlanStep, ...]
    state: PlanState = PlanState.DRAFT

    def __post_init__(self) -> None:
        if not isinstance(self.plan_id, str) or not self.plan_id.strip() or len(self.plan_id) > 128:
            raise PlanValidationError("plan_id must be a non-empty bounded string.")
        if not isinstance(self.objective, str) or not self.objective.strip() or len(self.objective) > MAX_PLAN_TEXT:
            raise PlanValidationError("Plan objective must be a non-empty bounded string.")
        if not isinstance(self.acceptance_criteria, tuple) or not self.acceptance_criteria:
            raise PlanValidationError("At least one acceptance criterion is required.")
        if any(not isinstance(item, str) or not item.strip() or len(item) > MAX_PLAN_TEXT for item in self.acceptance_criteria):
            raise PlanValidationError("Acceptance criteria must be non-empty bounded strings.")
        if not isinstance(self.steps, tuple) or not 1 <= len(self.steps) <= MAX_PLAN_STEPS:
            raise PlanValidationError(f"A plan must contain between 1 and {MAX_PLAN_STEPS} steps.")
        if not isinstance(self.state, PlanState):
            raise PlanValidationError("state must be a recognized PlanState.")
        ids = [step.step_id for step in self.steps]
        if len(set(ids)) != len(ids):
            raise PlanValidationError("Step identifiers must be unique.")
        known = set(ids)
        for step in self.steps:
            missing = set(step.depends_on) - known
            if missing:
                raise PlanValidationError(f"Step {step.step_id} has unknown dependencies.")
            if step.step_id in step.depends_on:
                raise PlanValidationError("A step cannot depend on itself.")
        self.topological_order()  # Reject dependency cycles at construction.

    def topological_order(self) -> tuple[str, ...]:
        by_id = {step.step_id: step for step in self.steps}
        remaining = {step.step_id: set(step.depends_on) for step in self.steps}
        ordered: list[str] = []
        while remaining:
            ready = sorted(step_id for step_id, deps in remaining.items() if not deps)
            if not ready:
                raise PlanValidationError("Plan dependencies contain a cycle.")
            for step_id in ready:
                ordered.append(step_id)
                remaining.pop(step_id)
                for deps in remaining.values():
                    deps.discard(step_id)
        return tuple(ordered)

    @property
    def requires_human_approval(self) -> bool:
        return any(
            step.risk in {RiskClass.EXTERNAL_SIDE_EFFECT, RiskClass.PRIVILEGED}
            for step in self.steps
        )

    def mark_ready(self) -> "ProfessorPlan":
        if self.state is not PlanState.DRAFT:
            raise PlanValidationError("Only a draft plan can become ready.")
        target = PlanState.AWAITING_APPROVAL if self.requires_human_approval else PlanState.READY
        return ProfessorPlan(
            plan_id=self.plan_id,
            objective=self.objective,
            acceptance_criteria=self.acceptance_criteria,
            steps=self.steps,
            state=target,
        )

    def approve(self, *, approval_reference: str) -> "ProfessorPlan":
        if self.state is not PlanState.AWAITING_APPROVAL or not self.requires_human_approval:
            raise PlanValidationError("This plan is not awaiting approval.")
        if not isinstance(approval_reference, str) or not approval_reference.strip() or len(approval_reference) > 256:
            raise PlanValidationError("An action-bound approval reference is required.")
        return ProfessorPlan(
            plan_id=self.plan_id,
            objective=self.objective,
            acceptance_criteria=self.acceptance_criteria,
            steps=self.steps,
            state=PlanState.APPROVED,
        )
