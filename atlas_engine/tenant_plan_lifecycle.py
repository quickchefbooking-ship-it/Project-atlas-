"""Safe tenant plan preparation boundary: validate policy, then mark READY.

This route never approves, claims, dispatches or executes a step. A plan can
become READY only when every step is structurally eligible under the trusted
application capability catalogue and the verified caller's scopes.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .capability_registry import CapabilityRegistry
from .http_identity import require_verified_principal
from .identity_policy import AuthorizationDenied
from .orchestration_coordinator import preview_plan
from .plan_contract import PlanState, ProfessorPlan
from .tenant_plan_repository import (
    TenantPlanConflict,
    TenantPlanNotFound,
    TenantPlanRepository,
)

router = APIRouter()


def _readiness_payload(preview):
    return {
        "plan_id": preview.plan_id,
        "plan_state": preview.plan_state.value,
        "ordered_step_ids": list(preview.ordered_step_ids),
        "structurally_ready_step_ids": list(preview.structurally_ready_step_ids),
        "blocked_step_ids": list(preview.blocked_step_ids),
        "execution_enabled": False,
        "steps": [
            {
                "step_id": item.step_id,
                "capability": item.capability,
                "capability_version": item.capability_version,
                "readiness": item.readiness.value,
                "reasons": list(item.reasons),
            }
            for item in preview.steps
        ],
    }


@router.post("/professor/tenant/plans/{plan_id}/prepare")
def prepare_tenant_professor_plan(
    plan_id: str,
    request: Request,
    principal=Depends(require_verified_principal),
):
    """Validate a DRAFT against trusted capability policy before marking READY."""
    database_path = getattr(request.app.state, "tenant_data_path", None)
    if not database_path:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tenant plan storage is not configured.",
        )
    registry = getattr(request.app.state, "tenant_capability_registry", None)
    if not isinstance(registry, CapabilityRegistry):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Trusted capability catalogue is not configured.",
        )

    connection = sqlite3.connect(database_path, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        repository = TenantPlanRepository(connection, principal)
        plan = repository.get(plan_id)
        if plan.state is not PlanState.DRAFT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only a DRAFT plan can be prepared.",
            )

        candidate = ProfessorPlan(
            plan_id=plan.plan_id,
            objective=plan.objective,
            acceptance_criteria=plan.acceptance_criteria,
            steps=plan.steps,
            state=PlanState.READY,
            approval_reference=None,
        )
        preview = preview_plan(
            candidate, registry, granted_scopes=principal.scopes
        )
        if preview.blocked_step_ids:
            return {
                "status": "blocked",
                "state": PlanState.DRAFT.value,
                "readiness": _readiness_payload(preview),
                "execution_enabled": False,
            }

        ready_plan = repository.transition(
            plan_id,
            expected_state=PlanState.DRAFT,
            new_state=PlanState.READY,
        )
        return {
            "status": "prepared",
            "plan_id": ready_plan.plan_id,
            "tenant_id": principal.tenant_id,
            "state": ready_plan.state.value,
            "readiness": _readiness_payload(preview),
            "execution_enabled": False,
            "next_boundary": "Human review and action-bound approval remain separate; no execution is available.",
        }
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Tenant plan preparation denied.") from None
    except TenantPlanNotFound:
        raise HTTPException(status_code=404, detail="Plan was not found.") from None
    except TenantPlanConflict:
        raise HTTPException(status_code=409, detail="Plan state changed; inspect it before retrying.") from None
    except sqlite3.Error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tenant plan storage is temporarily unavailable.",
        ) from None
    finally:
        connection.close()
