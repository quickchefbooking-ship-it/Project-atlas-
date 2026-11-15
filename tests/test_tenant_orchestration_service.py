import sqlite3
import pytest

from atlas_engine.capability_registry import CapabilityDefinition, CapabilityRegistry
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.plan_contract import PlanState, PlanStep, ProfessorPlan, RiskClass
from atlas_engine.tenant_plan_repository import TenantPlanRepository
from atlas_engine.tenant_step_execution_repository import TenantStepExecutionRepository
from atlas_engine.tenant_orchestration_service import TenantProfessorOrchestrationService


SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def make_plan(state=PlanState.DRAFT):
    return ProfessorPlan("tenant-plan", "Research a question", ("Cite evidence",), (
        PlanStep("search", "knowledge.search", "Find sources", RiskClass.READ_ONLY,
                 required_scopes=("knowledge:read",), capability_version="1"),
    ), state=state)


def setup():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    from atlas_engine.tenant_plan_repository import initialize_tenant_plan_schema
    initialize_tenant_plan_schema(db)
    principal = RequestPrincipal("issuer", "subject-a", "tenant-a", True, frozenset({
        "plans:read", "plans:write", "steps:read", "steps:claim",
        "steps:heartbeat", "steps:complete", "knowledge:read",
    }))
    plans = TenantPlanRepository(db, principal)
    steps = TenantStepExecutionRepository(db, principal)
    registry = CapabilityRegistry((CapabilityDefinition(
        "knowledge.search", "1", "read_only", SCHEMA, SCHEMA,
        required_scopes=("knowledge:read",),
    ),))
    service = TenantProfessorOrchestrationService(principal, plans, steps, registry)
    return db, principal, plans, steps, registry, service


def test_inspection_composes_plan_transitions_steps_and_policy_preview():
    _, _, plans, _, _, service = setup()
    p = make_plan()
    plans.create(p)
    plans.transition(p.plan_id, expected_state=PlanState.DRAFT, new_state=PlanState.READY)
    report = service.inspect_plan(p.plan_id)
    assert report.tenant_id == "tenant-a"
    assert report.plan.state is PlanState.READY
    assert len(report.transitions) == 2
    assert len(report.steps) == 1
    assert report.readiness is not None
    assert report.readiness.structurally_ready_step_ids == ("search",)
    assert report.execution_enabled is False
    assert "no capability handler" in report.execution_block_reason


def test_running_plan_inspection_reports_state_but_never_dispatches():
    _, _, plans, steps, _, service = setup()
    p = make_plan()
    plans.create(p)
    plans.transition(p.plan_id, expected_state=PlanState.DRAFT, new_state=PlanState.READY)
    plans.transition(p.plan_id, expected_state=PlanState.READY, new_state=PlanState.RUNNING)
    lease = steps.claim_next_step(p.plan_id, "worker-a")
    report = service.inspect_plan(p.plan_id)
    assert report.plan.state is PlanState.RUNNING
    assert report.readiness is None
    assert report.steps[0].state == "claimed"
    assert report.recent_events[0].event_type == "claimed"
    assert report.execution_enabled is False
    assert "does not dispatch" in report.execution_block_reason


def test_cross_tenant_plan_inspection_is_not_found():
    db, principal, _, _, registry, _ = setup()
    other = RequestPrincipal("issuer", "subject-b", "tenant-b", True, principal.scopes)
    service = TenantProfessorOrchestrationService(
        other, TenantPlanRepository(db, other),
        TenantStepExecutionRepository(db, other), registry,
    )
    with pytest.raises(LookupError):
        service.inspect_plan("tenant-plan")


def test_service_rejects_repositories_with_different_principals():
    db, principal, plans, _, registry, _ = setup()
    other = RequestPrincipal("issuer", "subject-b", "tenant-b", True, principal.scopes)
    with pytest.raises(ValueError, match="same immutable request principal"):
        TenantProfessorOrchestrationService(
            principal, plans, TenantStepExecutionRepository(db, other), registry
        )


def test_readiness_preview_fails_closed_when_caller_lacks_capability_scope():
    db, principal, plans, steps, registry, _ = setup()
    restricted = RequestPrincipal("issuer", "reader", "tenant-a", True,
                                  frozenset({"plans:read", "steps:read"}))
    restricted_service = TenantProfessorOrchestrationService(
        restricted, TenantPlanRepository(db, restricted),
        TenantStepExecutionRepository(db, restricted), registry,
    )
    plans.create(make_plan())
    plans.transition("tenant-plan", expected_state=PlanState.DRAFT, new_state=PlanState.READY)
    report = restricted_service.inspect_plan("tenant-plan")
    assert report.readiness.blocked_step_ids == ("search",)
    assert report.readiness.steps[0].readiness.value == "blocked_scope_mismatch"


def test_report_event_limit_is_bounded():
    _, _, plans, _, _, service = setup()
    plans.create(make_plan())
    with pytest.raises(ValueError):
        service.inspect_plan("tenant-plan", event_limit_per_step=0)


def test_service_rejects_repositories_on_different_database_connections():
    _, principal, plans, _, registry, _ = setup()
    other_db = sqlite3.connect(":memory:")
    from atlas_engine.tenant_plan_repository import initialize_tenant_plan_schema
    initialize_tenant_plan_schema(other_db)
    other_steps = TenantStepExecutionRepository(other_db, principal)
    with pytest.raises(ValueError, match="share one database connection"):
        TenantProfessorOrchestrationService(principal, plans, other_steps, registry)
