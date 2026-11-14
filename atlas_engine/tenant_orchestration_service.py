"""Tenant-aware, non-executing Professor orchestration facade.

Composes the isolated tenant plan and step repositories with the trusted
application capability registry. This layer reports readiness and persisted
execution state only; it never dispatches work.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .capability_registry import CapabilityRegistry
from .identity_policy import RequestPrincipal
from .orchestration_coordinator import PlanPreview, preview_plan
from .plan_contract import PlanState, ProfessorPlan
from .tenant_plan_repository import TenantPlanRepository, TenantPlanTransition
from .tenant_step_execution_repository import (
    TenantStepEvent,
    TenantStepExecutionRepository,
    TenantStepRecord,
)


@dataclass(frozen=True)
class TenantProfessorReport:
    tenant_id: str
    plan: ProfessorPlan
    transitions: tuple[TenantPlanTransition, ...]
    steps: tuple[TenantStepRecord, ...]
    recent_events: tuple[TenantStepEvent, ...]
    readiness: PlanPreview | None
    execution_enabled: bool
    execution_block_reason: str


class TenantProfessorOrchestrationService:
    """Read-only composition of tenant-owned plans, steps and capability policy."""

    def __init__(
        self,
        principal: RequestPrincipal,
        plans: TenantPlanRepository,
        steps: TenantStepExecutionRepository,
        registry: CapabilityRegistry,
    ) -> None:
        if not isinstance(principal, RequestPrincipal):
            raise TypeError("A trusted RequestPrincipal is required.")
        if not isinstance(plans, TenantPlanRepository):
            raise TypeError("A TenantPlanRepository is required.")
        if not isinstance(steps, TenantStepExecutionRepository):
            raise TypeError("A TenantStepExecutionRepository is required.")
        if not isinstance(registry, CapabilityRegistry):
            raise TypeError("A trusted CapabilityRegistry is required.")
        if plans.principal != principal or steps.principal != principal:
            raise ValueError("All repositories must use the same immutable request principal.")
        self.principal = principal
        self.plans = plans
        self.steps = steps
        self.registry = registry

    def inspect_plan(self, plan_id: str, *, event_limit_per_step: int = 20) -> TenantProfessorReport:
        """Return tenant-filtered plan state and a policy-only readiness preview."""
        if isinstance(event_limit_per_step, bool) or not isinstance(event_limit_per_step, int) or not 1 <= event_limit_per_step <= 100:
            raise ValueError("event_limit_per_step must be between 1 and 100.")
        plan = self.plans.get(plan_id)
        step_records = tuple(self.steps.list_steps(plan_id))
        transitions = tuple(self.plans.list_transitions(plan_id))
        events: list[TenantStepEvent] = []
        for step in step_records:
            events.extend(self.steps.list_events(
                plan_id, step.step_id, limit=event_limit_per_step
            ))
        events.sort(key=lambda item: item.created_at)
        readiness: PlanPreview | None = None
        reason = "Execution is disabled in this prototype; this report is observational only."
        if plan.state is PlanState.READY:
            readiness = preview_plan(
                plan, self.registry, granted_scopes=self.principal.scopes
            )
            reason = "Readiness preview only; no capability handler or worker is invoked."
        elif plan.state in {PlanState.DRAFT, PlanState.AWAITING_APPROVAL, PlanState.APPROVED}:
            reason = "Plan state does not permit a runnable readiness preview."
        elif plan.state is PlanState.RUNNING:
            reason = "Existing step ownership is reported only; this service does not dispatch or resume work."
        return TenantProfessorReport(
            tenant_id=self.principal.tenant_id,
            plan=plan,
            transitions=transitions,
            steps=step_records,
            recent_events=tuple(events),
            readiness=readiness,
            execution_enabled=False,
            execution_block_reason=reason,
        )
