import json
import sqlite3
import pytest

import atlas_engine.tenant_step_execution_repository as step_module
from atlas_engine.identity_policy import AuthorizationDenied, RequestPrincipal
from atlas_engine.plan_contract import PlanState, PlanStep, ProfessorPlan, RiskClass
from atlas_engine.tenant_plan_repository import TenantPlanRepository, initialize_tenant_plan_schema
from atlas_engine.tenant_step_execution_repository import (
    TenantStepConflict, TenantStepError, TenantStepNotFound,
    TenantStepPlanNotRunning, TenantStepExecutionRepository,
)


@pytest.fixture
def setup():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    initialize_tenant_plan_schema(db)
    scopes = frozenset({"plans:read", "plans:write", "steps:read",
                        "steps:claim", "steps:heartbeat", "steps:complete"})
    alice = RequestPrincipal("issuer", "alice", "tenant-a", True, scopes)
    bob = RequestPrincipal("issuer", "bob", "tenant-b", True, scopes)
    plans_a = TenantPlanRepository(db, alice)
    plans_b = TenantPlanRepository(db, bob)
    steps_a = TenantStepExecutionRepository(db, alice)
    steps_b = TenantStepExecutionRepository(db, bob)
    return db, plans_a, plans_b, steps_a, steps_b


def plan(pid="plan-a", risk=RiskClass.READ_ONLY):
    return ProfessorPlan(pid, "Run safe research", ("Evidence is recorded",), (
        PlanStep("first", "knowledge.search", "Find evidence", risk),
        PlanStep("second", "knowledge.summarise", "Summarise", RiskClass.LOCAL_COMPUTATION,
                 depends_on=("first",)),
    ))


def running(plans, p=None):
    p = p or plan()
    plans.create(p)
    plans.transition(p.plan_id, expected_state=PlanState.DRAFT, new_state=PlanState.READY)
    plans.transition(p.plan_id, expected_state=PlanState.READY, new_state=PlanState.RUNNING)
    return p


def test_tenant_claim_and_completion_flow_and_dependency_gate(setup):
    _, plans, _, steps, _ = setup
    p = running(plans)
    lease = steps.claim_next_step(p.plan_id, "worker-a", 30)
    assert lease.step_id == "first"
    assert steps.claim_next_step(p.plan_id, "worker-b") is None
    done = steps.complete(lease, result={"evidence": ["source-1"]})
    assert done.state == "succeeded"
    second = steps.claim_next_step(p.plan_id, "worker-b")
    assert second.step_id == "second"
    steps.complete(second, result={"summary": "checked"})
    assert [x.state for x in steps.list_steps(p.plan_id)] == ["succeeded", "succeeded"]


def test_cross_tenant_cannot_inspect_claim_heartbeat_or_complete(setup):
    _, plans_a, plans_b, steps_a, steps_b = setup
    p = running(plans_a)
    lease = steps_a.claim_next_step(p.plan_id, "worker-a")
    with pytest.raises(TenantStepNotFound):
        steps_b.get_step(p.plan_id, "first")
    with pytest.raises(TenantStepNotFound):
        steps_b.list_steps(p.plan_id)
    with pytest.raises(TenantStepNotFound):
        steps_b.list_events(p.plan_id, "first")
    with pytest.raises(TenantStepNotFound):
        steps_b.claim_next_step(p.plan_id, "worker-b")
    with pytest.raises(TenantStepConflict):
        steps_b.heartbeat(lease)
    with pytest.raises(TenantStepConflict):
        steps_b.complete(lease, result={"cross": "tenant"})
    assert steps_a.get_step(p.plan_id, "first").state == "claimed"


def test_plan_must_be_running(setup):
    _, plans, _, steps, _ = setup
    p = plan()
    plans.create(p)
    with pytest.raises(TenantStepPlanNotRunning):
        steps.claim_next_step(p.plan_id, "worker-a")


def test_expired_lease_is_recovery_required_and_never_replayed(setup, monkeypatch):
    _, plans, _, steps, _ = setup
    p = running(plans)
    now = 1_900_000_000.0
    monkeypatch.setattr(step_module.time, "time", lambda: now)
    lease = steps.claim_next_step(p.plan_id, "worker-a", 1)
    monkeypatch.setattr(step_module.time, "time", lambda: now + 2)
    assert steps.claim_next_step(p.plan_id, "worker-b") is None
    assert steps.get_step(p.plan_id, "first").state == "recovery_required"
    with pytest.raises(TenantStepConflict):
        steps.complete(lease, result={"late": True})
    events = steps.list_events(p.plan_id, "first")
    assert events[-1].event_type == "lease_expired"
    assert events[-1].details["automatic_replay"] is False


def test_recovery_resolution_requires_scope_and_marks_uncertain_work_failed(setup, monkeypatch):
    db, plans, _, steps, _ = setup
    p = running(plans)
    now = 1_900_000_000.0
    monkeypatch.setattr(step_module.time, "time", lambda: now)
    lease = steps.claim_next_step(p.plan_id, "worker-a", 1)
    monkeypatch.setattr(step_module.time, "time", lambda: now + 2)
    assert steps.claim_next_step(p.plan_id, "worker-b") is None

    with pytest.raises(AuthorizationDenied):
        steps.resolve_recovery_as_failed(
            p.plan_id, "first", expected_fencing_token=lease.fencing_token,
            reason="Reviewed timeout; outcome cannot be established",
        )

    reviewer = RequestPrincipal(
        "issuer", "operator-1", "tenant-a", True,
        frozenset({"steps:read", "steps:recover"}),
    )
    recovery = TenantStepExecutionRepository(db, reviewer)
    resolved = recovery.resolve_recovery_as_failed(
        p.plan_id, "first", expected_fencing_token=lease.fencing_token,
        reason="Reviewed timeout; outcome cannot be established",
    )
    assert resolved.state == "failed"
    assert resolved.error_code == "operator_marked_failed"
    assert resolved.result is None
    events = recovery.list_events(p.plan_id, "first")
    assert events[-1].event_type == "failed"
    assert events[-1].details == {
        "decision": "operator_marked_failed",
        "reason": "Reviewed timeout; outcome cannot be established",
        "actor_issuer": "issuer",
        "actor_subject": "operator-1",
        "automatic_replay": False,
    }
    assert recovery.claim_next_step(p.plan_id, "worker-c") is None


def test_recovery_resolution_rejects_stale_fencing_token_and_non_recovery_state(setup, monkeypatch):
    db, plans, _, steps, _ = setup
    p = running(plans)
    now = 1_900_000_000.0
    monkeypatch.setattr(step_module.time, "time", lambda: now)
    lease = steps.claim_next_step(p.plan_id, "worker-a", 1)
    monkeypatch.setattr(step_module.time, "time", lambda: now + 2)
    assert steps.claim_next_step(p.plan_id, "worker-b") is None

    reviewer = RequestPrincipal(
        "issuer", "operator-1", "tenant-a", True,
        frozenset({"steps:read", "steps:recover"}),
    )
    recovery = TenantStepExecutionRepository(db, reviewer)
    with pytest.raises(TenantStepConflict, match="stale fencing token"):
        recovery.resolve_recovery_as_failed(
            p.plan_id, "first", expected_fencing_token=lease.fencing_token + 1,
            reason="Reviewed uncertain execution",
        )
    resolved = recovery.resolve_recovery_as_failed(
        p.plan_id, "first", expected_fencing_token=lease.fencing_token,
        reason="Reviewed uncertain execution",
    )
    with pytest.raises(TenantStepConflict, match="Only recovery-required"):
        recovery.resolve_recovery_as_failed(
            p.plan_id, "first", expected_fencing_token=lease.fencing_token,
            reason="Attempt to resolve twice",
        )
    assert resolved.state == "failed"


def test_recovery_resolution_is_tenant_scoped_and_validates_reason(setup, monkeypatch):
    db, plans_a, _, steps_a, steps_b = setup
    p = running(plans_a)
    now = 1_900_000_000.0
    monkeypatch.setattr(step_module.time, "time", lambda: now)
    lease = steps_a.claim_next_step(p.plan_id, "worker-a", 1)
    monkeypatch.setattr(step_module.time, "time", lambda: now + 2)
    assert steps_a.claim_next_step(p.plan_id, "worker-b") is None

    operator_a = RequestPrincipal(
        "issuer", "operator-a", "tenant-a", True,
        frozenset({"steps:read", "steps:recover"}),
    )
    operator_b = RequestPrincipal(
        "issuer", "operator-b", "tenant-b", True,
        frozenset({"steps:read", "steps:recover"}),
    )
    recovery_a = TenantStepExecutionRepository(db, operator_a)
    recovery_b = TenantStepExecutionRepository(db, operator_b)
    with pytest.raises(TenantStepNotFound):
        recovery_b.resolve_recovery_as_failed(
            p.plan_id, "first", expected_fencing_token=lease.fencing_token,
            reason="Cross tenant attempt",
        )
    with pytest.raises(ValueError, match="reason"):
        recovery_a.resolve_recovery_as_failed(
            p.plan_id, "first", expected_fencing_token=lease.fencing_token,
            reason="   ",
        )
    with pytest.raises(ValueError, match="positive integer"):
        recovery_a.resolve_recovery_as_failed(
            p.plan_id, "first", expected_fencing_token=True,
            reason="Invalid token type",
        )
    assert recovery_a.get_step(p.plan_id, "first").state == "recovery_required"


def test_worker_ownership_and_fencing_are_enforced(setup):
    _, plans, _, steps, _ = setup
    p = running(plans)
    lease = steps.claim_next_step(p.plan_id, "worker-a")
    forged = type(lease)(lease.tenant_id, lease.plan_id, lease.step_id, "worker-b",
                         lease.attempt_number, lease.fencing_token, lease.lease_expires_at)
    with pytest.raises(TenantStepConflict):
        steps.complete(forged, result={"forged": True})
    renewed = steps.heartbeat(lease, 90)
    assert renewed.fencing_token == lease.fencing_token
    assert renewed.lease_expires_at > lease.lease_expires_at


def test_external_and_privileged_steps_are_blocked(setup):
    _, plans, _, steps, _ = setup
    p = plan("external", RiskClass.EXTERNAL_SIDE_EFFECT)
    running(plans, p)
    with pytest.raises(TenantStepError, match="action-bound authorisation"):
        steps.claim_next_step(p.plan_id, "worker-a")
    assert steps.get_step(p.plan_id, "first").state == "pending"


def test_dedicated_scopes_and_active_membership_required(setup):
    db, plans, _, _, _ = setup
    p = running(plans)
    read_only = RequestPrincipal("issuer", "reader", "tenant-a", True,
                                 frozenset({"steps:read"}))
    from atlas_engine.tenant_step_execution_repository import initialize_tenant_step_schema
    reader = TenantStepExecutionRepository(db, read_only)
    with pytest.raises(AuthorizationDenied):
        reader.claim_next_step(p.plan_id, "worker")
    inactive = RequestPrincipal("issuer", "inactive", "tenant-a", False,
                                frozenset({"steps:claim"}))
    denied = TenantStepExecutionRepository(db, inactive)
    with pytest.raises(AuthorizationDenied):
        denied.claim_next_step(p.plan_id, "worker")


def test_result_is_finite_and_bounded_json(setup):
    _, plans, _, steps, _ = setup
    p = running(plans)
    lease = steps.claim_next_step(p.plan_id, "worker-a")
    with pytest.raises(ValueError, match="finite JSON"):
        steps.complete(lease, result={"n": float("nan")})
    with pytest.raises(ValueError, match="64 KiB"):
        steps.complete(lease, result={"text": "x" * 70_000})


def test_event_history_is_append_only(setup):
    db, plans, _, steps, _ = setup
    p = running(plans)
    lease = steps.claim_next_step(p.plan_id, "worker-a")
    steps.complete(lease, result={"ok": True})
    events = steps.list_events(p.plan_id, "first")
    assert [e.event_type for e in events] == ["claimed", "succeeded"]
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("UPDATE tenant_professor_step_events SET details_json='{}' WHERE event_id=1")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("DELETE FROM tenant_professor_step_events WHERE event_id=1")


def test_step_rows_are_composite_tenant_scoped(setup):
    db, plans, _, steps, _ = setup
    p = running(plans)
    steps.list_steps(p.plan_id)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("""INSERT INTO tenant_professor_step_runs
          (tenant_id,plan_id,step_id,state) VALUES('tenant-b',?,'first','pending')""",
          (p.plan_id,))


def test_worker_must_hold_each_steps_declared_scopes():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    from atlas_engine.tenant_plan_repository import initialize_tenant_plan_schema
    initialize_tenant_plan_schema(db)
    principal = RequestPrincipal("issuer", "worker", "tenant-a", True,
                                 frozenset({"plans:read", "plans:write", "steps:claim"}))
    plans = TenantPlanRepository(db, principal)
    steps = TenantStepExecutionRepository(db, principal)
    p = ProfessorPlan("scoped", "Read protected knowledge", ("Respect access",), (
        PlanStep("read", "knowledge.private", "Read private source", RiskClass.READ_ONLY,
                 required_scopes=("private:read",)),
    ))
    plans.create(p)
    plans.transition(p.plan_id, expected_state=PlanState.DRAFT, new_state=PlanState.READY)
    plans.transition(p.plan_id, expected_state=PlanState.READY, new_state=PlanState.RUNNING)
    with pytest.raises(TenantStepError, match="lacks required step scopes"):
        steps.claim_next_step(p.plan_id, "worker-a")
    row = db.execute("""SELECT state FROM tenant_professor_step_runs
        WHERE tenant_id='tenant-a' AND plan_id='scoped' AND step_id='read'""").fetchone()
    assert row is not None and row["state"] == "pending"

def test_dependency_results_hands_off_only_completed_direct_dependency_outputs(setup):
    _, plans, _, steps, _ = setup
    p = running(plans)
    first = steps.claim_next_step(p.plan_id, "worker-a")
    steps.complete(first, result={"provider": "Crossref", "sources": [{"doi": "10.1/a"}]})
    assert steps.dependency_results(p.plan_id, "second") == {
        "first": {"provider": "Crossref", "sources": [{"doi": "10.1/a"}]}
    }


def test_dependency_results_refuses_pending_or_failed_dependencies(setup):
    _, plans, _, steps, _ = setup
    p = running(plans)
    with pytest.raises(TenantStepConflict, match="must succeed"):
        steps.dependency_results(p.plan_id, "second")


def test_dependency_results_cannot_read_another_tenants_plan(setup):
    _, plans_a, _, steps_a, steps_b = setup
    p = running(plans_a)
    first = steps_a.claim_next_step(p.plan_id, "worker-a")
    steps_a.complete(first, result={"private": "tenant-a"})
    with pytest.raises(TenantStepNotFound):
        steps_b.dependency_results(p.plan_id, "second")


def test_dependency_results_rejects_unrelated_step_ids(setup):
    _, plans, _, steps, _ = setup
    p = running(plans)
    with pytest.raises(TenantStepNotFound):
        steps.dependency_results(p.plan_id, "not-a-step")
