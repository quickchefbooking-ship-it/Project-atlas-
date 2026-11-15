"""One-step-at-a-time execution for Professor's bounded capability slice.

Only trusted application-owned handlers are callable. Public research is
read-only and source-attributed; external writes, privileged actions, arbitrary
plugins and task-supplied handlers remain unavailable.
"""
from __future__ import annotations

import hashlib
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .capability_runtime import CapabilityExecutionError, CapabilityRuntime
from .http_identity import require_verified_principal
from .identity_policy import AuthorizationDenied, authorize_tenant_resource
from .orchestration_coordinator import preview_plan
from .plan_contract import PlanState
from .tenant_plan_repository import TenantPlanConflict, TenantPlanNotFound, TenantPlanRepository
from .tenant_execution_audit_repository import TenantExecutionAuditRepository
from .tenant_step_execution_repository import (
    TenantStepError, TenantStepExecutionRepository,
)

router = APIRouter()


def _worker_id(principal) -> str:
    digest = hashlib.sha256(
        (principal.issuer + "\\0" + principal.subject).encode("utf-8")
    ).hexdigest()[:32]
    return "http:" + digest


@router.post("/professor/tenant/plans/{plan_id}/execute-next")
def execute_next_tenant_professor_step(
    plan_id: str,
    request: Request,
    principal=Depends(require_verified_principal),
):
    """Execute exactly one eligible local-computation step and persist its outcome."""
    try:
        authorize_tenant_resource(principal, principal.tenant_id, {"plans:execute"})
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Plan execution denied.") from None

    # This process-wide gate is checked on every request, before storage access,
    # plan inspection, capability lookup or handler dispatch. Missing state fails closed.
    if getattr(request.app.state, "capability_execution_enabled", False) is not True:
        raise HTTPException(
            status_code=503,
            detail="Capability execution is globally disabled.",
        )

    database_path = getattr(request.app.state, "tenant_data_path", None)
    runtime = getattr(request.app.state, "tenant_capability_runtime", None)
    if not database_path or not isinstance(runtime, CapabilityRuntime):
        raise HTTPException(status_code=503, detail="Professor execution is not configured.")

    connection = sqlite3.connect(database_path, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        plans = TenantPlanRepository(connection, principal)
        steps = TenantStepExecutionRepository(connection, principal)
        plan = plans.get(plan_id)
        if plan.state is PlanState.READY:
            preview = preview_plan(plan, runtime.registry, granted_scopes=principal.scopes)
            if preview.blocked_step_ids:
                raise HTTPException(status_code=409, detail="Plan is not eligible for execution.")
            plan = plans.transition(
                plan_id, expected_state=PlanState.READY, new_state=PlanState.RUNNING
            )
        elif plan.state is not PlanState.RUNNING:
            raise HTTPException(status_code=409, detail="Plan is not in a runnable state.")
        else:
            # A running plan cannot use preview_plan: that preview is deliberately
            # limited to READY/APPROVED plans. Recheck only dependency-ready,
            # not-yet-completed steps against fresh membership scopes before the
            # repository attempts to claim one (which otherwise masks revocation
            # as a generic 409 conflict).
            records = steps.list_steps(plan_id)
            states = {item.step_id: item.state for item in records}
            for candidate in plan.steps:
                if states.get(candidate.step_id) != "pending":
                    continue
                if any(states.get(dependency) != "succeeded" for dependency in candidate.depends_on):
                    continue
                version = candidate.capability_version
                if version is None:
                    matches = [
                        item.version for item in runtime.registry.list_definitions()
                        if item.name == candidate.capability
                    ]
                    version = matches[0] if len(matches) == 1 else None
                definition = runtime.registry.get(candidate.capability, version) if version else None
                required_scopes = set(candidate.required_scopes)
                if definition is None:
                    plans.transition(
                        plan_id, expected_state=PlanState.RUNNING, new_state=PlanState.FAILED
                    )
                    raise HTTPException(status_code=409, detail="The planned capability is not installed.")
                required_scopes.update(definition.required_scopes)
                if not required_scopes.issubset(principal.scopes):
                    plans.transition(
                        plan_id, expected_state=PlanState.RUNNING, new_state=PlanState.FAILED
                    )
                    raise HTTPException(
                        status_code=403,
                        detail="Required capability permissions are no longer available; the plan has been stopped.",
                    )

        worker_id = _worker_id(principal)
        lease = steps.claim_next_step(plan_id, worker_id, lease_seconds=60)
        if lease is None:
            records = steps.list_steps(plan_id)
            states = {item.state for item in records}
            if states == {"succeeded"}:
                completed = plans.transition(
                    plan_id, expected_state=PlanState.RUNNING, new_state=PlanState.SUCCEEDED
                )
                return {
                    "status": "completed", "plan_id": plan_id,
                    "plan_state": completed.state.value, "execution_enabled": True,
                }
            if states.intersection({"failed", "recovery_required", "cancelled"}):
                return {
                    "status": "blocked", "plan_id": plan_id,
                    "plan_state": plan.state.value,
                    "step_states": {item.step_id: item.state for item in records},
                    "execution_enabled": True,
                    "next_action": "Operator review is required; no automatic replay is performed.",
                }
            raise HTTPException(status_code=409, detail="No dependency-ready step is available.")

        step = next(item for item in plan.steps if item.step_id == lease.step_id)
        version = step.capability_version
        if version is None:
            matches = [
                item.version for item in runtime.registry.list_definitions()
                if item.name == step.capability
            ]
            version = matches[0] if len(matches) == 1 else None
        if version is None:
            steps.complete(lease, error_code="capability_not_found")
            plans.transition(
                plan_id, expected_state=PlanState.RUNNING, new_state=PlanState.FAILED
            )
            raise HTTPException(status_code=409, detail="The planned capability is not installed.")

        # Membership scopes are resolved afresh for every HTTP request. A plan
        # may span several execute-next calls, so re-check the exact step's
        # declared and registry-required scopes after claiming it and before
        # invoking its handler. If access was withdrawn, terminalise the
        # claimed step and stop the plan rather than leaving a live lease.
        definition = runtime.registry.get(step.capability, version)
        if definition is None:
            steps.complete(lease, error_code="capability_not_found")
            plans.transition(
                plan_id, expected_state=PlanState.RUNNING, new_state=PlanState.FAILED
            )
            raise HTTPException(status_code=409, detail="The planned capability is not installed.")
        required_scopes = set(step.required_scopes) | set(definition.required_scopes)
        if not required_scopes.issubset(principal.scopes):
            steps.complete(lease, error_code="capability_scope_revoked")
            plans.transition(
                plan_id, expected_state=PlanState.RUNNING, new_state=PlanState.FAILED
            )
            raise HTTPException(
                status_code=403,
                detail="Required capability permissions are no longer available; the plan has been stopped.",
            )

        try:
            # Capability-specific input mapping is derived from the trusted
            # registered schema. The plan objective is data, never executable code.
            dependency_outputs = steps.dependency_results(plan_id, step.step_id)
            capability_input = runtime.input_for_objective(
                step.capability, version, step.objective,
                dependency_outputs=dependency_outputs,
            )
            # The committed reservation is a hard precondition for dispatch.
            # If its transaction fails, runtime.execute is never reached.
            audit = TenantExecutionAuditRepository(connection, principal)
            reservation_event_id = audit.reserve(
                plan_id=plan_id,
                step_id=step.step_id,
                capability=step.capability,
                capability_version=version,
                attempt_number=lease.attempt_number,
                fencing_token=lease.fencing_token,
                capability_input=capability_input,
            )
            result = runtime.execute(
                step.capability, version, capability_input,
                timeout_seconds=step.timeout_seconds,
            )
            audit.record_outcome(
                reservation_event_id, event_type="handler_succeeded", output=result
            )
            record = steps.complete(lease, result=result)
        except CapabilityExecutionError:
            if "reservation_event_id" in locals():
                audit.record_outcome(
                    reservation_event_id,
                    event_type="handler_failed",
                    error_code="capability_execution_failed",
                )
            steps.complete(lease, error_code="capability_execution_failed")
            plans.transition(
                plan_id, expected_state=PlanState.RUNNING, new_state=PlanState.FAILED
            )
            return {
                "status": "failed", "plan_id": plan_id, "step_id": lease.step_id,
                "plan_state": PlanState.FAILED.value,
                "error_code": "capability_execution_failed",
                "execution_enabled": True,
            }

        records = steps.list_steps(plan_id)
        all_succeeded = all(item.state == "succeeded" for item in records)
        plan_state = PlanState.RUNNING.value
        if all_succeeded:
            completed = plans.transition(
                plan_id, expected_state=PlanState.RUNNING, new_state=PlanState.SUCCEEDED
            )
            plan_state = completed.state.value
        return {
            "status": "completed" if all_succeeded else "step_succeeded",
            "plan_id": plan_id,
            "step_id": record.step_id,
            "step_state": record.state,
            "result": record.result,
            "plan_state": plan_state,
            "execution_enabled": True,
            "next_action": None if all_succeeded else "Call execute-next again for the next dependency-ready step.",
        }
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Tenant execution scope denied.") from None
    except TenantPlanNotFound:
        raise HTTPException(status_code=404, detail="Plan was not found.") from None
    except (TenantPlanConflict, TenantStepError):
        raise HTTPException(status_code=409, detail="Plan or step ownership changed; inspect before retrying.") from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Tenant execution storage is temporarily unavailable.") from None
    finally:
        connection.close()
