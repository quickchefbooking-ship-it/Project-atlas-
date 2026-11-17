"""One-step-at-a-time execution for Professor's bounded capability slice.

Only trusted application-owned handlers are callable. Public research is
read-only and source-attributed; external writes, privileged actions, arbitrary
plugins and task-supplied handlers remain unavailable.
"""
from __future__ import annotations

import hashlib
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

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
from .tenant_plan_cancellation import (
    CancellationPlanNotActive, CancellationPlanNotFound,
    TenantPlanCancellationRepository,
)

router = APIRouter()


class CancelTenantPlanRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


def _finalize_requested_cancellation(plans, steps, cancellations, plan_id: str):
    """Stop future claims; let already-claimed bounded work finish safely."""
    if not cancellations.is_requested(plan_id):
        return None

    plan = plans.get(plan_id)
    records = ()
    if plan.state in {PlanState.RUNNING, PlanState.CANCELLED}:
        records = steps.list_steps(plan_id)
    states = {item.step_id: item.state for item in records}

    if plan.state is PlanState.RUNNING and any(
        item.state == "claimed" for item in records
    ):
        return {
            "status": "cancellation_requested",
            "plan_id": plan_id,
            "plan_state": plan.state.value,
            "step_states": states,
            "execution_enabled": True,
            "next_action": (
                "An already-claimed step may finish; no additional steps will be claimed."
            ),
        }

    if plan.state in {PlanState.READY, PlanState.RUNNING}:
        plan = plans.transition(
            plan_id, expected_state=plan.state, new_state=PlanState.CANCELLED
        )

    if plan.state is PlanState.CANCELLED:
        recovery_required = any(
            item.state == "recovery_required" for item in records
        )
        return {
            "status": "cancelled",
            "plan_id": plan_id,
            "plan_state": plan.state.value,
            "step_states": states,
            "execution_enabled": True,
            "next_action": (
                "Operator review is required for an uncertain expired lease; no automatic replay is performed."
                if recovery_required else None
            ),
        }

    return {
        "status": "already_terminal",
        "plan_id": plan_id,
        "plan_state": plan.state.value,
        "execution_enabled": True,
        "next_action": None,
    }


def _worker_id(principal) -> str:
    digest = hashlib.sha256(
        (principal.issuer + "\\0" + principal.subject).encode("utf-8")
    ).hexdigest()[:32]
    return "http:" + digest


@router.post("/professor/tenant/plans/{plan_id}/cancel")
def request_tenant_professor_plan_cancellation(
    plan_id: str,
    body: CancelTenantPlanRequest,
    request: Request,
    principal=Depends(require_verified_principal),
):
    """Persist a tenant-authorized stop request without interrupting a live handler."""
    database_path = getattr(request.app.state, "tenant_data_path", None)
    if not database_path:
        raise HTTPException(status_code=503, detail="Professor execution storage is not configured.")
    connection = sqlite3.connect(database_path, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        cancellations = TenantPlanCancellationRepository(connection, principal)
        record = cancellations.request(plan_id, reason=body.reason)
        return {
            "status": "cancellation_requested",
            "plan_id": record.plan_id,
            "requested_at": record.requested_at,
        }
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Plan cancellation denied.") from None
    except CancellationPlanNotFound:
        raise HTTPException(status_code=404, detail="Plan was not found.") from None
    except CancellationPlanNotActive:
        raise HTTPException(status_code=409, detail="Plan is not cancellable in its current state.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Tenant execution storage is temporarily unavailable.") from None
    finally:
        connection.close()


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
        cancellations = TenantPlanCancellationRepository(connection, principal)
        plan = plans.get(plan_id)
        cancellation_result = _finalize_requested_cancellation(
            plans, steps, cancellations, plan_id
        )
        if cancellation_result is not None:
            return cancellation_result

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
            cancellation_result = _finalize_requested_cancellation(
                plans, steps, cancellations, plan_id
            )
            if cancellation_result is not None:
                return cancellation_result
            records = steps.list_steps(plan_id)
            states = {item.state for item in records}
            if states == {"succeeded"}:
                try:
                    completed = plans.transition(
                        plan_id, expected_state=PlanState.RUNNING, new_state=PlanState.SUCCEEDED
                    )
                except TenantPlanConflict:
                    cancellation_result = _finalize_requested_cancellation(
                        plans, steps, cancellations, plan_id
                    )
                    if cancellation_result is not None:
                        return cancellation_result
                    raise
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

        # A cancellation may arrive after the HTTP-level preflight but before
        # the lease is dispatched. Release this claim as a failed-before-run
        # attempt; it must never be replayed automatically.
        if cancellations.is_requested(plan_id):
            steps.complete(lease, error_code="cancelled_before_dispatch")
            cancellation_result = _finalize_requested_cancellation(
                plans, steps, cancellations, plan_id
            )
            if cancellation_result is not None:
                return cancellation_result

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
            # Recheck after the durable audit reservation and immediately
            # before dispatch. A later request is treated as an in-flight step
            # and may finish, but no subsequent step can be claimed.
            if cancellations.is_requested(plan_id):
                audit.record_outcome(
                    reservation_event_id,
                    event_type="handler_failed",
                    error_code="cancelled_before_dispatch",
                )
                steps.complete(lease, error_code="cancelled_before_dispatch")
                cancellation_result = _finalize_requested_cancellation(
                    plans, steps, cancellations, plan_id
                )
                if cancellation_result is not None:
                    return cancellation_result

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
            cancellation_result = _finalize_requested_cancellation(
                plans, steps, cancellations, plan_id
            )
            if cancellation_result is not None:
                cancellation_result.update({
                    "step_id": lease.step_id,
                    "step_state": "failed",
                    "error_code": "capability_execution_failed",
                })
                return cancellation_result
            plans.transition(
                plan_id, expected_state=PlanState.RUNNING, new_state=PlanState.FAILED
            )
            return {
                "status": "failed", "plan_id": plan_id, "step_id": lease.step_id,
                "plan_state": PlanState.FAILED.value,
                "error_code": "capability_execution_failed",
                "execution_enabled": True,
            }

        cancellation_result = _finalize_requested_cancellation(
            plans, steps, cancellations, plan_id
        )
        if cancellation_result is not None:
            cancellation_result.update({
                "step_id": record.step_id,
                "step_state": record.state,
                "result": record.result,
            })
            return cancellation_result

        records = steps.list_steps(plan_id)
        all_succeeded = all(item.state == "succeeded" for item in records)
        plan_state = PlanState.RUNNING.value
        if all_succeeded:
            try:
                completed = plans.transition(
                    plan_id, expected_state=PlanState.RUNNING, new_state=PlanState.SUCCEEDED
                )
                plan_state = completed.state.value
            except TenantPlanConflict:
                cancellation_result = _finalize_requested_cancellation(
                    plans, steps, cancellations, plan_id
                )
                if cancellation_result is not None:
                    cancellation_result.update({
                        "step_id": record.step_id,
                        "step_state": record.state,
                        "result": record.result,
                    })
                    return cancellation_result
                raise
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
