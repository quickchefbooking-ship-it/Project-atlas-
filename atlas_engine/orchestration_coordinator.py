"""Non-executing dependency and policy preview for Professor plans.

This module computes which plan steps are structurally eligible for a future
executor. It never invokes handlers, performs I/O, or treats an opaque approval
reference as verified authorisation.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .capability_registry import CapabilityRegistry
from .plan_contract import PlanState, ProfessorPlan, RiskClass


class StepReadiness(str, Enum):
    STRUCTURALLY_READY = "structurally_ready"
    BLOCKED_PLAN_STATE = "blocked_plan_state"
    BLOCKED_MISSING_CAPABILITY = "blocked_missing_capability"
    BLOCKED_RISK_MISMATCH = "blocked_risk_mismatch"
    BLOCKED_SCOPE_MISMATCH = "blocked_scope_mismatch"
    BLOCKED_DEPENDENCY = "blocked_dependency"
    APPROVAL_UNVERIFIED = "approval_unverified"


@dataclass(frozen=True)
class StepPreview:
    step_id: str
    capability: str
    capability_version: str | None
    readiness: StepReadiness
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PlanPreview:
    plan_id: str
    plan_state: PlanState
    ordered_step_ids: tuple[str, ...]
    steps: tuple[StepPreview, ...]
    structurally_ready_step_ids: tuple[str, ...]
    blocked_step_ids: tuple[str, ...]
    execution_enabled: bool = False


_RISK_LEVEL = {
    RiskClass.READ_ONLY: 0,
    RiskClass.LOCAL_COMPUTATION: 1,
    RiskClass.DRAFT_CREATION: 2,
    RiskClass.EXTERNAL_SIDE_EFFECT: 3,
    RiskClass.PRIVILEGED: 4,
}
_CAPABILITY_RISK = {
    "read_only": RiskClass.READ_ONLY,
    "local_write": RiskClass.DRAFT_CREATION,
    "external_write": RiskClass.EXTERNAL_SIDE_EFFECT,
    "privileged": RiskClass.PRIVILEGED,
}


def preview_plan(
    plan: ProfessorPlan,
    registry: CapabilityRegistry,
    *,
    granted_scopes: frozenset[str] | set[str] | tuple[str, ...] = (),
) -> PlanPreview:
    """Return a deterministic, fail-closed readiness preview without execution.

    The step's declared scopes must include all scopes declared by its
    registered capability, and the caller's granted scopes must include every
    scope requested by the step. A plan risk may be more restrictive than the
    capability's declared risk, never less restrictive.

    External/privileged steps remain blocked even when the plan carries an
    approval reference: the current reference is not cryptographically or
    identity-bound and cannot authorise execution.
    """
    if not isinstance(plan, ProfessorPlan):
        raise TypeError("A validated ProfessorPlan is required.")
    if not isinstance(registry, CapabilityRegistry):
        raise TypeError("A trusted CapabilityRegistry is required.")
    if not isinstance(granted_scopes, (set, frozenset, tuple, list)) or any(
        not isinstance(scope, str) or not scope.strip() for scope in granted_scopes
    ):
        raise ValueError("granted_scopes must contain non-empty strings.")
    granted = frozenset(granted_scopes)
    by_id = {step.step_id: step for step in plan.steps}
    previews: dict[str, StepPreview] = {}

    for step_id in plan.topological_order():
        step = by_id[step_id]
        version = step.capability_version or _find_version(registry, step.capability)
        definition = registry.get(step.capability, version) if version else None
        # Legacy plans may omit a version only when exactly one registered
        # version exists. Ambiguous names fail closed; never select "latest".
        if definition is None:
            previews[step_id] = StepPreview(
                step_id, step.capability, None,
                StepReadiness.BLOCKED_MISSING_CAPABILITY,
                ("No uniquely registered capability version matches this step.",),
            )
            continue

        if plan.state not in {PlanState.READY, PlanState.APPROVED}:
            previews[step_id] = StepPreview(
                step_id, step.capability, definition.version,
                StepReadiness.BLOCKED_PLAN_STATE,
                ("Plan must be ready before step coordination can proceed.",),
            )
            continue

        blocked_dependencies = tuple(
            dependency for dependency in step.depends_on
            if previews[dependency].readiness is not StepReadiness.STRUCTURALLY_READY
        )
        if blocked_dependencies:
            previews[step_id] = StepPreview(
                step_id, step.capability, definition.version,
                StepReadiness.BLOCKED_DEPENDENCY,
                ("Dependencies are not structurally ready: " + ", ".join(sorted(blocked_dependencies)),),
            )
            continue

        declared_risk = _CAPABILITY_RISK[definition.risk_class]
        if _RISK_LEVEL[step.risk] < _RISK_LEVEL[declared_risk]:
            previews[step_id] = StepPreview(
                step_id, step.capability, definition.version,
                StepReadiness.BLOCKED_RISK_MISMATCH,
                ("Plan step risk is less restrictive than the registered capability risk.",),
            )
            continue

        missing_capability_scopes = set(definition.required_scopes) - set(step.required_scopes)
        missing_grants = set(step.required_scopes) - granted
        if missing_capability_scopes or missing_grants:
            reasons = []
            if missing_capability_scopes:
                reasons.append(
                    "Plan step omits capability scopes: " + ", ".join(sorted(missing_capability_scopes))
                )
            if missing_grants:
                reasons.append("Caller lacks scopes: " + ", ".join(sorted(missing_grants)))
            previews[step_id] = StepPreview(
                step_id, step.capability, definition.version,
                StepReadiness.BLOCKED_SCOPE_MISMATCH, tuple(reasons),
            )
            continue

        if (
            definition.approval_required
            or definition.side_effects
            or definition.risk_class in {"external_write", "privileged"}
            or step.risk in {RiskClass.EXTERNAL_SIDE_EFFECT, RiskClass.PRIVILEGED}
        ):
            previews[step_id] = StepPreview(
                step_id, step.capability, definition.version,
                StepReadiness.APPROVAL_UNVERIFIED,
                ("An approval reference is not verified identity or action-bound authorisation.",),
            )
            continue

        previews[step_id] = StepPreview(
            step_id, step.capability, definition.version,
            StepReadiness.STRUCTURALLY_READY, (),
        )

    ordered = plan.topological_order()
    result_steps = tuple(previews[step_id] for step_id in ordered)
    ready = tuple(
        item.step_id for item in result_steps
        if item.readiness is StepReadiness.STRUCTURALLY_READY
    )
    blocked = tuple(
        item.step_id for item in result_steps
        if item.readiness is not StepReadiness.STRUCTURALLY_READY
    )
    return PlanPreview(
        plan_id=plan.plan_id,
        plan_state=plan.state,
        ordered_step_ids=ordered,
        steps=result_steps,
        structurally_ready_step_ids=ready,
        blocked_step_ids=blocked,
        execution_enabled=False,
    )


def _find_version(registry: CapabilityRegistry, capability_name: str) -> str:
    """Resolve only an unambiguous registered version; never guess latest."""
    matches = [
        definition.version for definition in registry.list_definitions()
        if definition.name == capability_name
    ]
    return matches[0] if len(matches) == 1 else ""
