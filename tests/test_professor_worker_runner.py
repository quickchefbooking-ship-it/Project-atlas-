import sqlite3

import pytest

from atlas_engine.capability_runtime import build_default_capability_runtime
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.plan_contract import PlanState, PlanStep, ProfessorPlan, RiskClass
from atlas_engine.professor_autonomy_policy import AutonomyMode, ProfessorAutonomyPolicy
from atlas_engine.professor_worker_identity import (
    ProfessorWorkerIdentityConfig,
    ProfessorWorkerIdentityService,
    WORKER_CONTROL_SCOPES,
    WorkerTenantGrant,
    WorkerIdentityUnavailable,
)
from atlas_engine.professor_worker_runner import (
    ProfessorWorkerGate,
    ProfessorWorkerRepositories,
    ProfessorWorkerRunner,
)
from atlas_engine.tenant_execution_audit_repository import TenantExecutionAuditRepository
from atlas_engine.tenant_plan_cancellation import TenantPlanCancellationRepository
from atlas_engine.tenant_plan_repository import TenantPlanRepository, initialize_tenant_plan_schema
from atlas_engine.tenant_step_execution_repository import TenantStepExecutionRepository


def make_plan(capability="math.calculate", version="1.0.0",
              risk=RiskClass.LOCAL_COMPUTATION, scopes=("compute:local",)):
    return ProfessorPlan("worker-plan", "Calculate 6 * 7", ("Record the result",), (
        PlanStep("calculate", capability, "6 * 7", risk,
                 required_scopes=scopes, capability_version=version),
    ))


def setup_runner(*, gate=None, capability="math.calculate", version="1.0.0",
                 risk=RiskClass.LOCAL_COMPUTATION, scopes=("compute:local",),
                 enabled=True):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    initialize_tenant_plan_schema(db)

    human = RequestPrincipal(
        "https://identity.example", "owner", "tenant-a", True,
        frozenset({"plans:read", "plans:write"}),
    )
    human_plans = TenantPlanRepository(db, human)
    plan = make_plan(capability, version, risk, scopes)
    human_plans.create(plan)
    human_plans.transition(plan.plan_id, expected_state=PlanState.DRAFT,
                           new_state=PlanState.READY)
    human_plans.transition(plan.plan_id, expected_state=PlanState.READY,
                           new_state=PlanState.RUNNING)

    worker_scopes = WORKER_CONTROL_SCOPES | {"compute:local"}
    identity = ProfessorWorkerIdentityService(ProfessorWorkerIdentityConfig(
        worker_id="professor-worker-test",
        enabled=enabled,
        tenant_grants=(WorkerTenantGrant("tenant-a", worker_scopes),) if enabled else (),
    ))

    def repositories_for(principal):
        return ProfessorWorkerRepositories(
            plans=TenantPlanRepository(db, principal),
            steps=TenantStepExecutionRepository(db, principal),
            cancellation=TenantPlanCancellationRepository(db, principal),
            audit=TenantExecutionAuditRepository(db, principal),
        )

    gate_reader = gate or (lambda: ProfessorWorkerGate(True, True, True))
    runner = ProfessorWorkerRunner(
        identity=identity,
        repositories_for=repositories_for,
        runtime=build_default_capability_runtime(),
        policy=ProfessorAutonomyPolicy(AutonomyMode.SANDBOX_BUILD),
        read_gate=gate_reader,
    )
    return db, human, runner, repositories_for, plan


def test_worker_is_disabled_by_default_and_does_not_claim():
    db, _, runner, repos, plan = setup_runner(gate=lambda: ProfessorWorkerGate())
    result = runner.tick_once("tenant-a", plan.plan_id)
    assert result.status == "disabled"
    assert db.execute("SELECT name FROM sqlite_master WHERE name='tenant_professor_step_runs'").fetchone() is None


def test_worker_executes_exactly_one_registered_local_step_and_audits_it():
    db, _, runner, repos, plan = setup_runner()
    result = runner.tick_once("tenant-a", plan.plan_id)
    assert result.status == "succeeded"
    assert result.step_id == "calculate"
    steps = repos(runner._identity.principal_for_tenant("tenant-a")).steps
    record = steps.get_step(plan.plan_id, "calculate")
    assert record.state == "succeeded"
    assert record.result == {"value": 42, "kind": "number"}
    events = db.execute(
        "SELECT event_type FROM tenant_professor_execution_audit ORDER BY event_id"
    ).fetchall()
    assert [row[0] for row in events] == ["execution_reserved", "handler_succeeded"]
    assert runner.tick_once("tenant-a", plan.plan_id).status == "idle"


def test_global_kill_switch_is_rechecked_before_dispatch():
    snapshots = iter((
        ProfessorWorkerGate(True, True, True),
        ProfessorWorkerGate(False, True, True),
    ))
    db, _, runner, repos, plan = setup_runner(gate=lambda: next(snapshots))
    result = runner.tick_once("tenant-a", plan.plan_id)
    assert result.status == "stopped_before_dispatch"
    assert db.execute("SELECT COUNT(*) FROM tenant_professor_execution_audit").fetchone()[0] == 0
    steps = repos(runner._identity.principal_for_tenant("tenant-a")).steps
    assert steps.get_step(plan.plan_id, "calculate").state == "claimed"


def test_unsupported_networked_capability_is_rejected_before_claim():
    db, _, runner, repos, plan = setup_runner(
        capability="research.crossref.search", version="1.0.0",
        risk=RiskClass.READ_ONLY, scopes=("research:public",),
    )
    result = runner.tick_once("tenant-a", plan.plan_id)
    assert result.status == "unsupported_plan"
    assert db.execute("SELECT COUNT(*) FROM tenant_professor_step_runs").fetchone()[0] == 0


def test_disabled_worker_identity_fails_closed():
    _, _, runner, _, plan = setup_runner(enabled=False)
    with pytest.raises(WorkerIdentityUnavailable):
        runner.tick_once("tenant-a", plan.plan_id)


def test_missing_isolation_proof_keeps_worker_disabled():
    _, _, runner, _, plan = setup_runner(
        gate=lambda: ProfessorWorkerGate(True, True, False)
    )
    assert runner.tick_once("tenant-a", plan.plan_id).status == "disabled"


def test_tenant_without_explicit_worker_grant_is_denied():
    _, _, runner, _, plan = setup_runner()
    with pytest.raises(WorkerIdentityUnavailable):
        runner.tick_once("tenant-b", plan.plan_id)

def test_cancellation_before_claim_prevents_any_step_claim():
    db, human, runner, repos, plan = setup_runner()
    cancellation = TenantPlanCancellationRepository(db, human)
    cancellation.request(plan.plan_id, reason="Owner requested stop")
    result = runner.tick_once("tenant-a", plan.plan_id)
    assert result.status == "cancelled"
    assert db.execute("SELECT COUNT(*) FROM tenant_professor_step_runs").fetchone()[0] == 0


def test_global_stop_after_audit_reservation_prevents_handler_dispatch():
    snapshots = iter((
        ProfessorWorkerGate(True, True, True),
        ProfessorWorkerGate(True, True, True),
        ProfessorWorkerGate(False, True, True),
    ))
    db, _, runner, repos, plan = setup_runner(gate=lambda: next(snapshots))
    result = runner.tick_once("tenant-a", plan.plan_id)
    assert result.status == "stopped_before_dispatch"
    events = db.execute(
        "SELECT event_type, details_json FROM tenant_professor_execution_audit ORDER BY event_id"
    ).fetchall()
    assert [row[0] for row in events] == ["execution_reserved", "handler_failed"]
    assert "stopped_before_dispatch" in events[-1][1]
