"""Read-only service that connects persisted Professor plans to coordination previews."""
from __future__ import annotations

from .capability_registry import CapabilityRegistry
from .orchestration_coordinator import PlanPreview, preview_plan
from .plan_repository import PlanRepository


class ProfessorOrchestrationService:
    """Load a persisted plan and produce a fail-closed coordination preview.

    This service intentionally has no executor dependency and exposes no
    mutation method. It is the application seam for a future authenticated
    preview endpoint; it does not start or resume work.
    """

    def __init__(
        self,
        *,
        plans: PlanRepository,
        capabilities: CapabilityRegistry,
    ) -> None:
        if not isinstance(plans, PlanRepository):
            raise TypeError("A PlanRepository is required.")
        if not isinstance(capabilities, CapabilityRegistry):
            raise TypeError("A trusted CapabilityRegistry is required.")
        self._plans = plans
        self._capabilities = capabilities

    def preview(
        self,
        plan_id: str,
        *,
        granted_scopes: frozenset[str] | set[str] | tuple[str, ...] = (),
    ) -> PlanPreview:
        """Return the current plan's readiness preview; never execute it."""
        plan = self._plans.get(plan_id)
        return preview_plan(
            plan,
            self._capabilities,
            granted_scopes=granted_scopes,
        )
