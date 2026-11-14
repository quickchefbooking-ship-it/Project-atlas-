import sqlite3

import pytest

import atlas_engine.step_execution_repository as step_repo
from atlas_engine.plan_contract import PlanState, PlanStep, ProfessorPlan, RiskClass
from atlas_engine.plan_repository import PlanRepository
from atlas_engine.step_execution_repository import (
    StepExecutionRepository,
    StepLeaseConflict,
    StepPlanNotRunning,
)


@pytest.fixture
def repositories(tmp_path):
    database = tmp_path / "professor-step-execution.db"

    def connect():
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    plans = PlanRepository(connection_factory=connect)
    steps = StepExecutionRepository(connection_factory=connect)
    return plans, steps


def make_plan():
    return ProfessorPlan(
        plan_id="step-plan",
        objective="Complete two ordered research steps",
        acceptance_criteria=("Both steps are recorded",),
        steps=(
            PlanStep("first", "knowledge.search", "Find sources", RiskClass.READ_ONLY),
            PlanStep(
                "second", "knowledge.summarise", "Summarise sources",
                RiskClass.READ_ONLY, depends_on=("first",),
            ),
        ),
    )


def start_plan(plans):
    plan = make_plan()
    plans.create(plan)
    plans.transition(
        plan.plan_id,
        expected_state=PlanState.DRAFT,
        new_state=PlanState.READY,
    )
    plans.transition(
        plan.plan_id,
        expected_state=PlanState.READY,
        new_state=PlanState.RUNNING,
    )
    return plan


def test_plan_creation_seeds_durable_pending_step_rows(repositories):
    plans, steps = repositories
    plan = make_plan()
    plans.create(plan)
    records = steps.list_steps(plan.plan_id)
    assert [item.step_id for item in records] == ["first", "second"]
    assert [item.state for item in records] == ["pending", "pending"]
    assert [item.ordinal for item in records] == [0, 1]


def test_steps_cannot_be_claimed_until_plan_is_running(repositories):
    plans, steps = repositories
    plan = make_plan()
    plans.create(plan)
    with pytest.raises(StepPlanNotRunning):
        steps.claim_next_step(plan.plan_id, "worker-a")


def test_claims_follow_dependencies_and_completion_is_persisted(repositories):
    plans, steps = repositories
    plan = start_plan(plans)

    first = steps.claim_next_step(plan.plan_id, "worker-a", lease_seconds=30)
    assert first is not None
    assert first.step_id == "first"
    assert steps.claim_next_step(plan.plan_id, "worker-b") is None

    completed = steps.complete(first, result={"sources": ["source-a"]})
    assert completed.state == "succeeded"
    assert completed.result == {"sources": ["source-a"]}

    second = steps.claim_next_step(plan.plan_id, "worker-b", lease_seconds=30)
    assert second is not None
    assert second.step_id == "second"
    steps.complete(second, result={"summary": "Checked summary"})
    assert [item.state for item in steps.list_steps(plan.plan_id)] == [
        "succeeded", "succeeded"
    ]


def test_claim_uses_a_fencing_token_and_records_an_append_only_event_history(repositories):
    plans, steps = repositories
    plan = start_plan(plans)
    lease = steps.claim_next_step(plan.plan_id, "worker-a")
    assert lease is not None
    renewed = steps.heartbeat(lease, lease_seconds=90)
    assert renewed.fencing_token == lease.fencing_token
    assert renewed.lease_expires_at > lease.lease_expires_at
    steps.complete(renewed, result={"ok": True})

    events = steps.list_events(plan.plan_id, "first")
    assert [event.event_type for event in events] == [
        "claimed", "heartbeat", "succeeded"
    ]
    assert all(event.fencing_token == lease.fencing_token for event in events)


def test_stale_worker_cannot_complete_after_lease_expiry(repositories, monkeypatch):
    plans, steps = repositories
    plan = start_plan(plans)
    now = 1_900_000_000.0
    monkeypatch.setattr(step_repo.time, "time", lambda: now)
    lease = steps.claim_next_step(plan.plan_id, "worker-a", lease_seconds=1)
    assert lease is not None

    monkeypatch.setattr(step_repo.time, "time", lambda: now + 2)
    assert steps.claim_next_step(plan.plan_id, "worker-b") is None
    assert steps.get_step(plan.plan_id, "first").state == "recovery_required"
    with pytest.raises(StepLeaseConflict):
        steps.complete(lease, result={"late": True})
    events = steps.list_events(plan.plan_id, "first")
    assert events[-1].event_type == "lease_expired"
    assert events[-1].details["automatic_replay"] is False


def test_failed_step_is_terminal_and_does_not_unlock_dependants(repositories):
    plans, steps = repositories
    plan = start_plan(plans)
    lease = steps.claim_next_step(plan.plan_id, "worker-a")
    assert lease is not None
    failed = steps.complete(lease, error_code="CAPABILITY_FAILED")
    assert failed.state == "failed"
    assert failed.error_code == "CAPABILITY_FAILED"
    assert steps.claim_next_step(plan.plan_id, "worker-b") is None


def test_step_result_must_be_finite_bounded_json(repositories):
    plans, steps = repositories
    plan = start_plan(plans)
    lease = steps.claim_next_step(plan.plan_id, "worker-a")
    assert lease is not None
    with pytest.raises(ValueError, match="finite JSON"):
        steps.complete(lease, result={"number": float("nan")})
    with pytest.raises(ValueError, match="64 KiB"):
        steps.complete(lease, result={"text": "x" * 70_000})


def test_old_fencing_token_cannot_overwrite_current_step_state(repositories):
    plans, steps = repositories
    plan = start_plan(plans)
    lease = steps.claim_next_step(plan.plan_id, "worker-a")
    assert lease is not None
    with pytest.raises(StepLeaseConflict):
        steps.complete(
            type(lease)(
                lease.plan_id, lease.step_id, "worker-b",
                lease.attempt_number, lease.fencing_token, lease.lease_expires_at,
            ),
            result={"forged": True},
        )
    assert steps.get_step(plan.plan_id, "first").state == "claimed"


def test_external_side_effect_and_privileged_steps_cannot_be_claimed(repositories):
    from atlas_engine.step_execution_repository import StepExecutionError

    plans, steps = repositories
    plan = ProfessorPlan(
        plan_id="restricted-plan",
        objective="Perform a protected action",
        acceptance_criteria=("Action is authorised",),
        steps=(
            PlanStep(
                "publish", "social.publish", "Publish externally",
                RiskClass.EXTERNAL_SIDE_EFFECT,
            ),
        ),
    )
    plans.create(plan)
    plans.transition(
        plan.plan_id,
        expected_state=PlanState.DRAFT,
        new_state=PlanState.AWAITING_APPROVAL,
    )
    plans.transition(
        plan.plan_id,
        expected_state=PlanState.AWAITING_APPROVAL,
        new_state=PlanState.APPROVED,
        approval_reference="opaque-reference",
    )
    plans.transition(
        plan.plan_id,
        expected_state=PlanState.APPROVED,
        new_state=PlanState.RUNNING,
    )
    with pytest.raises(StepExecutionError, match="action-bound authorisation"):
        steps.claim_next_step(plan.plan_id, "worker-a")
    assert steps.get_step(plan.plan_id, "publish").state == "pending"


def test_step_event_history_reads_are_bounded(repositories):
    plans, steps = repositories
    plan = start_plan(plans)
    lease = steps.claim_next_step(plan.plan_id, "worker-a")
    assert lease is not None
    for _ in range(3):
        lease = steps.heartbeat(lease, lease_seconds=60)
    steps.complete(lease, result={"done": True})
    assert len(steps.list_events(plan.plan_id, "first", limit=2)) == 2
    with pytest.raises(ValueError, match="limit"):
        steps.list_events(plan.plan_id, "first", limit=0)
