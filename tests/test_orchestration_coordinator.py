import pytest

from atlas_engine.capability_registry import CapabilityDefinition, CapabilityRegistry
from atlas_engine.orchestration_coordinator import StepReadiness, preview_plan
from atlas_engine.plan_contract import PlanStep, ProfessorPlan, RiskClass


def capability(
    name="knowledge.lookup",
    version="1",
    risk_class="read_only",
    required_scopes=(),
    side_effects=False,
    approval_required=False,
):
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    return CapabilityDefinition(
        name=name,
        version=version,
        risk_class=risk_class,
        input_schema=schema,
        output_schema=schema,
        required_scopes=tuple(required_scopes),
        side_effects=side_effects,
        approval_required=approval_required,
    )


def plan(steps, plan_id="preview-test"):
    return ProfessorPlan(
        plan_id=plan_id,
        objective="Coordinate a bounded research task",
        acceptance_criteria=("Return checked findings",),
        steps=tuple(steps),
    )


def test_preview_orders_dependencies_and_marks_only_structural_readiness():
    item = plan([
        PlanStep("second", "knowledge.lookup", "Summarise findings", RiskClass.READ_ONLY, depends_on=("first",)),
        PlanStep("first", "knowledge.lookup", "Retrieve sources", RiskClass.READ_ONLY),
    ]).mark_ready()
    result = preview_plan(item, CapabilityRegistry([capability()]))
    assert result.ordered_step_ids == ("first", "second")
    assert result.structurally_ready_step_ids == ("first", "second")
    assert result.blocked_step_ids == ()
    assert result.execution_enabled is False


def test_unknown_capability_fails_closed_and_blocks_dependants():
    item = plan([
        PlanStep("first", "missing.capability", "Do missing work", RiskClass.READ_ONLY),
        PlanStep("second", "knowledge.lookup", "Continue", RiskClass.READ_ONLY, depends_on=("first",)),
    ]).mark_ready()
    result = preview_plan(item, CapabilityRegistry([capability()]))
    assert result.steps[0].readiness is StepReadiness.BLOCKED_MISSING_CAPABILITY
    assert result.steps[1].readiness is StepReadiness.BLOCKED_DEPENDENCY


def test_plan_risk_cannot_understate_registered_capability_risk():
    item = plan([
        PlanStep("write", "files.save", "Save a local draft", RiskClass.READ_ONLY),
    ]).mark_ready()
    registry = CapabilityRegistry([capability(
        name="files.save", risk_class="local_write", required_scopes=("files:write",)
    )])
    result = preview_plan(item, registry, granted_scopes={"files:write"})
    assert result.steps[0].readiness is StepReadiness.BLOCKED_RISK_MISMATCH


def test_step_must_declare_capability_scopes_and_caller_must_have_them():
    item = plan([
        PlanStep("lookup", "knowledge.lookup", "Retrieve sources", RiskClass.READ_ONLY),
    ]).mark_ready()
    registry = CapabilityRegistry([capability(required_scopes=("knowledge:read",))])
    result = preview_plan(item, registry, granted_scopes={"knowledge:read"})
    assert result.steps[0].readiness is StepReadiness.BLOCKED_SCOPE_MISMATCH
    assert "Plan step omits capability scopes" in result.steps[0].reasons[0]


def test_caller_scope_missing_blocks_step():
    item = plan([
        PlanStep(
            "lookup", "knowledge.lookup", "Retrieve sources", RiskClass.READ_ONLY,
            required_scopes=("knowledge:read",),
        ),
    ]).mark_ready()
    registry = CapabilityRegistry([capability(required_scopes=("knowledge:read",))])
    result = preview_plan(item, registry, granted_scopes=())
    assert result.steps[0].readiness is StepReadiness.BLOCKED_SCOPE_MISMATCH
    assert "Caller lacks scopes" in result.steps[0].reasons[0]


def test_approval_reference_never_counts_as_verified_authorisation():
    item = plan([
        PlanStep(
            "publish", "social.publish", "Publish content",
            RiskClass.EXTERNAL_SIDE_EFFECT,
            required_scopes=("social:publish",),
        ),
    ])
    awaiting = item.mark_ready()
    approved = awaiting.approve(approval_reference="opaque-reference")
    registry = CapabilityRegistry([capability(
        name="social.publish",
        risk_class="external_write",
        required_scopes=("social:publish",),
        side_effects=True,
        approval_required=True,
    )])
    result = preview_plan(approved, registry, granted_scopes={"social:publish"})
    assert result.steps[0].readiness is StepReadiness.APPROVAL_UNVERIFIED
    assert result.execution_enabled is False


def test_coordinator_does_not_guess_between_capability_versions():
    item = plan([
        PlanStep("lookup", "knowledge.lookup", "Retrieve sources", RiskClass.READ_ONLY),
    ]).mark_ready()
    registry = CapabilityRegistry([
        capability(version="1"),
        capability(version="2"),
    ])
    result = preview_plan(item, registry)
    assert result.steps[0].readiness is StepReadiness.BLOCKED_MISSING_CAPABILITY


def test_non_ready_plan_is_blocked():
    item = plan([
        PlanStep("lookup", "knowledge.lookup", "Retrieve sources", RiskClass.READ_ONLY),
    ])
    result = preview_plan(item, CapabilityRegistry([capability()]))
    assert result.steps[0].readiness is StepReadiness.BLOCKED_PLAN_STATE


def test_invalid_scope_input_is_rejected():
    item = plan([
        PlanStep("lookup", "knowledge.lookup", "Retrieve sources", RiskClass.READ_ONLY),
    ]).mark_ready()
    with pytest.raises(ValueError, match="granted_scopes"):
        preview_plan(item, CapabilityRegistry([capability()]), granted_scopes={" "})


def test_plan_can_pin_an_exact_capability_version():
    item = plan([
        PlanStep(
            "lookup", "knowledge.lookup", "Retrieve sources", RiskClass.READ_ONLY,
            capability_version="2",
        ),
    ]).mark_ready()
    registry = CapabilityRegistry([
        capability(version="1"),
        capability(version="2"),
    ])
    result = preview_plan(item, registry)
    assert result.steps[0].readiness is StepReadiness.STRUCTURALLY_READY
    assert result.steps[0].capability_version == "2"
