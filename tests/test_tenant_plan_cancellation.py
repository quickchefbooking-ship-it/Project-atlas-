import sqlite3

import pytest

from atlas_engine.identity_policy import AuthorizationDenied, RequestPrincipal
from atlas_engine.plan_contract import PlanState, PlanStep, ProfessorPlan, RiskClass
from atlas_engine.tenant_plan_repository import TenantPlanRepository, initialize_tenant_plan_schema
from atlas_engine.tenant_plan_cancellation import (
    CancellationPlanNotActive,
    CancellationPlanNotFound,
    TenantPlanCancellationRepository,
)


@pytest.fixture
def setup():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    initialize_tenant_plan_schema(db)
    owner = RequestPrincipal(
        "issuer", "owner", "tenant-a", True,
        frozenset({"plans:read", "plans:write", "steps:read"}),
    )
    other = RequestPrincipal(
        "issuer", "other", "tenant-b", True,
        frozenset({"plans:read", "plans:write", "steps:read"}),
    )
    plans = TenantPlanRepository(db, owner)
    plan = ProfessorPlan("plan-a", "Bounded local work", ("Work stops safely",), (
        PlanStep("step-a", "math.calculate", "1 + 1", RiskClass.LOCAL_COMPUTATION),
    ))
    plans.create(plan)
    plans.transition(plan.plan_id, expected_state=PlanState.DRAFT, new_state=PlanState.READY)
    plans.transition(plan.plan_id, expected_state=PlanState.READY, new_state=PlanState.RUNNING)
    return db, owner, other, plan


def test_cancellation_request_is_durable_and_tenant_scoped(setup):
    db, owner, _, plan = setup
    repo = TenantPlanCancellationRepository(db, owner)
    request = repo.request(plan.plan_id, reason="Owner requested stop")
    assert request.tenant_id == "tenant-a"
    assert request.plan_id == plan.plan_id
    assert request.requested_by_subject == "owner"
    assert repo.is_requested(plan.plan_id) is True


def test_cancellation_is_idempotent_and_first_reason_is_preserved(setup):
    db, owner, _, plan = setup
    repo = TenantPlanCancellationRepository(db, owner)
    first = repo.request(plan.plan_id, reason="First stop")
    second = repo.request(plan.plan_id, reason="Second stop")
    assert first == second
    assert second.reason == "First stop"


def test_cross_tenant_cannot_request_or_observe_cancellation(setup):
    db, _, other, plan = setup
    repo = TenantPlanCancellationRepository(db, other)
    with pytest.raises(CancellationPlanNotFound):
        repo.request(plan.plan_id, reason="Cross tenant")
    with pytest.raises(CancellationPlanNotFound):
        repo.is_requested(plan.plan_id)


def test_missing_scopes_are_denied(setup):
    db, _, _, plan = setup
    reader = RequestPrincipal("issuer", "reader", "tenant-a", True, frozenset({"steps:read"}))
    repo = TenantPlanCancellationRepository(db, reader)
    with pytest.raises(AuthorizationDenied):
        repo.request(plan.plan_id, reason="No write")
    writer = RequestPrincipal("issuer", "writer", "tenant-a", True, frozenset({"plans:write"}))
    repo = TenantPlanCancellationRepository(db, writer)
    with pytest.raises(AuthorizationDenied):
        repo.is_requested(plan.plan_id)


def test_only_ready_or_running_plans_can_be_cancelled(setup):
    db, owner, _, plan = setup
    plans = TenantPlanRepository(db, owner)
    plans.transition(plan.plan_id, expected_state=PlanState.RUNNING, new_state=PlanState.SUCCEEDED)
    repo = TenantPlanCancellationRepository(db, owner)
    with pytest.raises(CancellationPlanNotActive):
        repo.request(plan.plan_id, reason="Too late")


def test_cancellation_history_cannot_be_updated_or_deleted(setup):
    db, owner, _, plan = setup
    repo = TenantPlanCancellationRepository(db, owner)
    repo.request(plan.plan_id, reason="Immutable")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute(
            "UPDATE tenant_professor_cancellation_requests SET reason='changed' WHERE tenant_id='tenant-a'"
        )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute(
            "DELETE FROM tenant_professor_cancellation_requests WHERE tenant_id='tenant-a'"
        )
