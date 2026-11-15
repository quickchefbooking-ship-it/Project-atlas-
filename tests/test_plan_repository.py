import sqlite3

import pytest

from atlas_engine.plan_contract import PlanState, PlanStep, ProfessorPlan, RiskClass
from atlas_engine.plan_repository import (
    PlanAlreadyExists,
    PlanNotFound,
    PlanRepository,
    PlanStateConflict,
)


@pytest.fixture
def repository(tmp_path):
    db_path = tmp_path / "professor-plans.db"

    def connect():
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    return PlanRepository(connection_factory=connect)


def make_plan(risk=RiskClass.READ_ONLY):
    return ProfessorPlan(
        plan_id="plan-test-1",
        objective="Prepare a research summary",
        acceptance_criteria=("Include source evidence",),
        steps=(
            PlanStep(
                step_id="research",
                capability="knowledge.search",
                objective="Find approved sources",
                risk=risk,
                required_scopes=("knowledge:read",),
                expected_output="Cited source notes",
            ),
        ),
    )


def test_plan_round_trips_through_sqlite(repository):
    original = ProfessorPlan(
        plan_id="plan-test-1",
        objective="Prepare a research summary",
        acceptance_criteria=("Include source evidence",),
        steps=(
            PlanStep(
                step_id="research",
                capability="knowledge.search",
                objective="Find approved sources",
                risk=RiskClass.READ_ONLY,
                capability_version="3",
            ),
        ),
    )
    repository.create(original)
    assert repository.get(original.plan_id) == original


def test_duplicate_plan_id_is_rejected(repository):
    repository.create(make_plan())
    with pytest.raises(PlanAlreadyExists):
        repository.create(make_plan())


def test_unknown_plan_is_not_found(repository):
    with pytest.raises(PlanNotFound):
        repository.get("missing")


def test_state_transition_uses_expected_state(repository):
    repository.create(make_plan())
    ready = repository.transition(
        "plan-test-1",
        expected_state=PlanState.DRAFT,
        new_state=PlanState.READY,
    )
    assert ready.state is PlanState.READY
    with pytest.raises(PlanStateConflict, match="not draft"):
        repository.transition(
            "plan-test-1",
            expected_state=PlanState.DRAFT,
            new_state=PlanState.READY,
        )


def test_approval_transition_requires_reference(repository):
    repository.create(make_plan(RiskClass.EXTERNAL_SIDE_EFFECT))
    repository.transition(
        "plan-test-1",
        expected_state=PlanState.DRAFT,
        new_state=PlanState.AWAITING_APPROVAL,
    )
    with pytest.raises(PlanStateConflict, match="approval reference"):
        repository.transition(
            "plan-test-1",
            expected_state=PlanState.AWAITING_APPROVAL,
            new_state=PlanState.APPROVED,
        )
    approved = repository.transition(
        "plan-test-1",
        expected_state=PlanState.AWAITING_APPROVAL,
        new_state=PlanState.APPROVED,
        approval_reference="approval-123",
    )
    assert approved.state is PlanState.APPROVED
    assert approved.approval_reference == "approval-123"
    assert repository.get("plan-test-1").approval_reference == "approval-123"
    history = repository.list_transitions("plan-test-1")
    assert [event.to_state for event in history] == [
        PlanState.DRAFT,
        PlanState.AWAITING_APPROVAL,
        PlanState.APPROVED,
    ]
    assert history[-1].from_state is PlanState.AWAITING_APPROVAL
    assert history[-1].approval_reference == "approval-123"


def test_illegal_state_transition_is_rejected(repository):
    repository.create(make_plan())
    with pytest.raises(PlanStateConflict, match="not allowed"):
        repository.transition(
            "plan-test-1",
            expected_state=PlanState.DRAFT,
            new_state=PlanState.RUNNING,
        )


def test_plan_listing_is_bounded_and_can_filter_by_state(repository):
    repository.create(make_plan())
    repository.create(
        ProfessorPlan(
            plan_id="plan-test-2",
            objective="Another task",
            acceptance_criteria=("Produce output",),
            steps=(PlanStep("step", "local.compute", "Compute", RiskClass.LOCAL_COMPUTATION),),
        )
    )
    repository.transition(
        "plan-test-1",
        expected_state=PlanState.DRAFT,
        new_state=PlanState.READY,
    )
    assert [p.plan_id for p in repository.list(state=PlanState.READY)] == ["plan-test-1"]
    assert len(repository.list(limit=1)) == 1
    with pytest.raises(ValueError):
        repository.list(limit=0)


def test_new_plans_cannot_be_created_in_a_non_draft_state(repository):
    plan = make_plan()
    approved = ProfessorPlan(
        plan_id=plan.plan_id,
        objective=plan.objective,
        acceptance_criteria=plan.acceptance_criteria,
        steps=plan.steps,
        state=PlanState.APPROVED,
        approval_reference="unverified-reference",
    )
    with pytest.raises(PlanStateConflict, match="created in draft"):
        repository.create(approved)


def test_approval_reference_is_rejected_for_non_approval_transition(repository):
    repository.create(make_plan())
    with pytest.raises(PlanStateConflict, match="only accepted when approving"):
        repository.transition(
            "plan-test-1",
            expected_state=PlanState.DRAFT,
            new_state=PlanState.READY,
            approval_reference="unexpected-reference",
        )


def test_plan_transition_history_records_creation_and_normal_transitions(repository):
    repository.create(make_plan())
    repository.transition(
        "plan-test-1",
        expected_state=PlanState.DRAFT,
        new_state=PlanState.READY,
    )
    history = repository.list_transitions("plan-test-1")
    assert len(history) == 2
    assert history[0].from_state is None
    assert history[0].to_state is PlanState.DRAFT
    assert history[1].from_state is PlanState.DRAFT
    assert history[1].to_state is PlanState.READY
    assert history[1].approval_reference is None


def test_plan_contract_approve_preserves_reference():
    plan = make_plan(RiskClass.EXTERNAL_SIDE_EFFECT)
    awaiting = plan.mark_ready()
    approved = awaiting.approve(approval_reference="approval-contract-1")
    assert approved.state is PlanState.APPROVED
    assert approved.approval_reference == "approval-contract-1"
