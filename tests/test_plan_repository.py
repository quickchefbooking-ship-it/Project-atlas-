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
    original = make_plan()
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
