"""Disabled-by-default, one-step Professor worker orchestration boundary.

This module does not create processes, containers, queues, or isolation. A trusted
deployment must provide a verified isolation gate and application-owned
repository/runtime composition before a worker tick can dispatch a capability.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .capability_runtime import CapabilityExecutionError, CapabilityRuntime
from .identity_policy import RequestPrincipal
from .plan_contract import PlanState, RiskClass
from .professor_autonomy_policy import (
    AutonomyAction,
    AutonomyMode,
    ProfessorAutonomyPolicy,
)
from .professor_worker_identity import ProfessorWorkerIdentityService
from .tenant_execution_audit_repository import TenantExecutionAuditRepository
from .tenant_plan_cancellation import TenantPlanCancellationRepository
from .tenant_plan_repository import TenantPlanRepository
from .tenant_step_execution_repository import (
    TenantStepExecutionRepository,
    TenantStepError,
)


@dataclass(frozen=True)
class ProfessorWorkerGate:
    """Trusted deployment snapshot; every field must be explicitly true."""

    worker_enabled: bool = False
    global_execution_enabled: bool = False
    isolation_verified: bool = False

    def __post_init__(self) -> None:
        for name in ("worker_enabled", "global_execution_enabled", "isolation_verified"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean.")


@dataclass(frozen=True)
class ProfessorWorkerRepositories:
    plans: TenantPlanRepository
    steps: TenantStepExecutionRepository
    cancellation: TenantPlanCancellationRepository
    audit: TenantExecutionAuditRepository


@dataclass(frozen=True)
class ProfessorWorkerResult:
    status: str
    tenant_id: str
    plan_id: str
    step_id: str | None = None
    error_code: str | None = None


class ProfessorWorkerRunner:
    """Execute at most one approved deterministic local-computation step per tick.

    All dependencies are supplied by trusted server composition. No task data
    can register handlers, choose tenants, supply credentials, or change gates.
    """

    _FIRST_SLICE = frozenset({("math.calculate", "1.0.0")})

    def __init__(
        self,
        *,
        identity: ProfessorWorkerIdentityService,
        repositories_for: Callable[[RequestPrincipal], ProfessorWorkerRepositories],
        runtime: CapabilityRuntime,
        policy: ProfessorAutonomyPolicy,
        read_gate: Callable[[], ProfessorWorkerGate],
    ) -> None:
        if not isinstance(identity, ProfessorWorkerIdentityService):
            raise TypeError("Trusted worker identity service is required.")
        if not callable(repositories_for) or not callable(read_gate):
            raise TypeError("Trusted repository and gate providers are required.")
        if not isinstance(runtime, CapabilityRuntime):
            raise TypeError("Application-owned capability runtime is required.")
        if not isinstance(policy, ProfessorAutonomyPolicy):
            raise TypeError("A trusted autonomy policy is required.")
        self._identity = identity
        self._repositories_for = repositories_for
        self._runtime = runtime
        self._policy = policy
        self._read_gate = read_gate

    def _enabled(self) -> bool:
        gate = self._read_gate()
        if not isinstance(gate, ProfessorWorkerGate):
            raise TypeError("The deployment gate provider returned an invalid snapshot.")
        return gate.worker_enabled and gate.global_execution_enabled and gate.isolation_verified

    def tick_once(self, tenant_id: str, plan_id: str) -> ProfessorWorkerResult:
        """Claim and process no more than one step; never loops or auto-replays."""
        if not isinstance(tenant_id, str) or not tenant_id.strip() or len(tenant_id) > 512:
            raise ValueError("A bounded tenant ID is required.")
        if not isinstance(plan_id, str) or not plan_id.strip() or len(plan_id) > 128:
            raise ValueError("A bounded plan ID is required.")

        if not self._enabled():
            return ProfessorWorkerResult("disabled", tenant_id, plan_id)

        principal = self._identity.principal_for_tenant(tenant_id)
        if principal.tenant_id != tenant_id:
            return ProfessorWorkerResult("denied", tenant_id, plan_id, error_code="tenant_identity_mismatch")
        repositories = self._repositories_for(principal)
        plan = repositories.plans.get(plan_id)
        if plan.state is not PlanState.RUNNING:
            return ProfessorWorkerResult("not_running", tenant_id, plan_id)

        # Reject an unsupported plan before claiming anything. This first
        # worker slice has one fixed, non-networked, no-side-effect handler.
        for step in plan.steps:
            if (
                (step.capability, step.capability_version) not in self._FIRST_SLICE
                or step.risk is not RiskClass.LOCAL_COMPUTATION
            ):
                return ProfessorWorkerResult("unsupported_plan", tenant_id, plan_id,
                                             error_code="capability_outside_first_slice")
        definition = self._runtime.registry.get("math.calculate", "1.0.0")
        if (
            definition is None
            or definition.risk_class != "local_computation"
            or definition.side_effects
            or definition.approval_required
            or not set(definition.required_scopes).issubset(principal.scopes)
            or any(
                not set(definition.required_scopes).issubset(set(step.required_scopes))
                for step in plan.steps
            )
        ):
            return ProfessorWorkerResult("denied", tenant_id, plan_id,
                                         error_code="capability_contract_denied")

        decision = self._policy.decide(AutonomyAction.EXECUTE_REGISTERED_LOCAL_CAPABILITY)
        if not decision.allowed or decision.requires_human_approval:
            return ProfessorWorkerResult("denied", tenant_id, plan_id,
                                         error_code="autonomy_policy_denied")

        if repositories.cancellation.is_requested(plan_id):
            return ProfessorWorkerResult("cancelled", tenant_id, plan_id)

        lease = repositories.steps.claim_next_step(plan_id, self._identity.config.worker_id, 60)
        if lease is None:
            return ProfessorWorkerResult("idle", tenant_id, plan_id)

        step = next((item for item in plan.steps if item.step_id == lease.step_id), None)
        if step is None or (step.capability, step.capability_version) not in self._FIRST_SLICE:
            # Do not dispatch an unexpected claim. Leave the fenced lease for
            # explicit recovery rather than silently retrying it.
            return ProfessorWorkerResult("recovery_required", tenant_id, plan_id,
                                         lease.step_id, "claimed_step_contract_mismatch")

        if not self._enabled() or repositories.cancellation.is_requested(plan_id):
            # No handler has run. The lease is deliberately not replayed;
            # expiry will move it to recovery_required for explicit review.
            return ProfessorWorkerResult("stopped_before_dispatch", tenant_id, plan_id,
                                         lease.step_id)

        payload = self._runtime.input_for_objective(
            step.capability, step.capability_version, step.objective
        )
        reservation = repositories.audit.reserve(
            plan_id=plan_id,
            step_id=step.step_id,
            capability=step.capability,
            capability_version=step.capability_version,
            attempt_number=lease.attempt_number,
            fencing_token=lease.fencing_token,
            capability_input=payload,
        )

        # Re-read both stop controls after the durable reservation and
        # immediately before invoking the fixed handler.
        if not self._enabled() or repositories.cancellation.is_requested(plan_id):
            repositories.audit.record_outcome(
                reservation, event_type="handler_failed",
                error_code="stopped_before_dispatch",
            )
            return ProfessorWorkerResult("stopped_before_dispatch", tenant_id, plan_id,
                                         lease.step_id)

        try:
            result = self._runtime.execute(
                step.capability, step.capability_version, payload,
                timeout_seconds=min(step.timeout_seconds, 10),
            )
        except CapabilityExecutionError:
            repositories.audit.record_outcome(
                reservation, event_type="handler_failed",
                error_code="capability_execution_failed",
            )
            repositories.steps.complete(lease, error_code="capability_execution_failed")
            return ProfessorWorkerResult("failed", tenant_id, plan_id,
                                         lease.step_id, "capability_execution_failed")

        # Never commit a result after cancellation or a global stop. The
        # claimed lease remains fenced and will require explicit recovery.
        if not self._enabled() or repositories.cancellation.is_requested(plan_id):
            repositories.audit.record_outcome(
                reservation, event_type="handler_failed",
                error_code="stopped_after_execution",
            )
            return ProfessorWorkerResult("recovery_required", tenant_id, plan_id,
                                         lease.step_id, "stopped_after_execution")

        repositories.audit.record_outcome(
            reservation, event_type="handler_succeeded", output=result
        )
        repositories.steps.complete(lease, result=result)
        return ProfessorWorkerResult("succeeded", tenant_id, plan_id, lease.step_id)
