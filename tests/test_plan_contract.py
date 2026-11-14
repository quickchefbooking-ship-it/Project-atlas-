import pytest

from atlas_engine.plan_contract import (
    PlanState,
    PlanStep,
    PlanValidationError,
    ProfessorPlan,
    RiskClass,
)


def step(step_id, deps=(), risk=RiskClass.READ_ONLY):
    return PlanStep(
        step_id=step_id,
        capability="knowledge.search",
        objective=f"Complete {step_id}",
        risk=risk,
        depends_on=deps,
        required_scopes=("knowledge:read",),
        expected_output="Evidence-backed result",
    )


def plan(*steps):
    return ProfessorPlan(
        plan_id="plan-1",
        objective="Research and summarize an approved topic",
        acceptance_criteria=("Summary includes cited evidence",),
        steps=tuple(steps),
    )


def test_plan_produces_deterministic_dependency_order():
    item = plan(step("final", ("research",)), step("research"))
    assert item.topological_order() == ("research", "final")


def test_plan_rejects_unknown_dependency():
    with pytest.raises(PlanValidationError, match="unknown"):
        plan(step("summary", ("missing",)))


def test_plan_rejects_dependency_cycle():
    with pytest.raises(PlanValidationError, match="cycle"):
        plan(step("a", ("b",)), step("b", ("a",)))


def test_plan_rejects_duplicate_step_ids():
    with pytest.raises(PlanValidationError, match="unique"):
        plan(step("same"), step("same"))


def test_read_only_plan_can_be_marked_ready_without_approval():
    ready = plan(step("research")).mark_ready()
    assert ready.state is PlanState.READY
    assert ready.requires_human_approval is False


def test_external_side_effect_plan_waits_for_human_approval():
    waiting = plan(step("publish", risk=RiskClass.EXTERNAL_SIDE_EFFECT)).mark_ready()
    assert waiting.state is PlanState.AWAITING_APPROVAL
    with pytest.raises(PlanValidationError, match="approval reference"):
        waiting.approve(approval_reference=" ")
    approved = waiting.approve(approval_reference="approval-record-123")
    assert approved.state is PlanState.APPROVED


def test_privileged_plan_also_requires_approval():
    assert plan(step("admin", risk=RiskClass.PRIVILEGED)).mark_ready().state is PlanState.AWAITING_APPROVAL


def test_cannot_approve_plan_that_does_not_require_approval():
    ready = plan(step("research")).mark_ready()
    with pytest.raises(PlanValidationError, match="not awaiting"):
        ready.approve(approval_reference="approval-1")


def test_step_timeout_and_budget_are_bounded():
    with pytest.raises(PlanValidationError, match="timeout"):
        PlanStep("x", "capability", "objective", RiskClass.READ_ONLY, timeout_seconds=901)
    with pytest.raises(PlanValidationError, match="resource_budget"):
        PlanStep("x", "capability", "objective", RiskClass.READ_ONLY, resource_budget=0)


def test_plan_requires_acceptance_criteria():
    with pytest.raises(PlanValidationError, match="acceptance"):
        ProfessorPlan("p", "objective", (), (step("one"),))
