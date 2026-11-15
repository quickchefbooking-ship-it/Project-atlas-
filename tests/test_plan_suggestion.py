import json

import pytest

from atlas_engine.capability_registry import CapabilityDefinition, CapabilityRegistry
from atlas_engine.plan_contract import PlanState, RiskClass
from atlas_engine.plan_suggestion import PlanSuggestionError, parse_plan_suggestion


def definition():
    return CapabilityDefinition(
        name="research.lookup",
        version="2",
        risk_class="read_only",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string", "minLength": 3}},
            "required": ["query"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
            "additionalProperties": False,
        },
        required_scopes=("public.research.read",),
        timeout_seconds=7,
    )


def proposal(**overrides):
    payload = {
        "objective": "Research a topic",
        "acceptance_criteria": ["Provide a cited summary"],
        "steps": [{
            "step_id": "lookup",
            "capability": "research.lookup",
            "objective": "Find reliable sources about the topic",
            "depends_on": [],
            "expected_output": "A list of relevant sources",
        }],
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_model_proposal_uses_registry_owned_risk_scopes_version_and_budget():
    registry = CapabilityRegistry([definition()])
    plan = parse_plan_suggestion(proposal(), plan_id="server-plan-1", registry=registry)

    step = plan.steps[0]
    assert plan.state is PlanState.DRAFT
    assert step.risk is RiskClass.READ_ONLY
    assert step.required_scopes == ("public.research.read",)
    assert step.capability_version == "2"
    assert step.timeout_seconds == 7
    assert step.resource_budget == 1


@pytest.mark.parametrize("forged", [
    {"risk": "read_only"},
    {"required_scopes": ["admin:*"]},
    {"capability_version": "999"},
    {"timeout_seconds": 900},
    {"resource_budget": 100},
])
def test_model_cannot_supply_trusted_policy_fields(forged):
    step = {
        "step_id": "lookup",
        "capability": "research.lookup",
        "objective": "Search",
        **forged,
    }
    registry = CapabilityRegistry([definition()])
    with pytest.raises(PlanSuggestionError, match="privileged fields"):
        parse_plan_suggestion(
            proposal(steps=[step]), plan_id="server-plan-2", registry=registry
        )


def test_unknown_capability_is_rejected():
    registry = CapabilityRegistry([definition()])
    step = {
        "step_id": "unknown",
        "capability": "shell.execute",
        "objective": "Run a command",
    }
    with pytest.raises(PlanSuggestionError, match="unavailable"):
        parse_plan_suggestion(
            proposal(steps=[step]), plan_id="server-plan-3", registry=registry
        )


def test_duplicate_json_fields_are_rejected():
    raw = '{"objective":"a","objective":"b","acceptance_criteria":["x"],"steps":[]}'
    with pytest.raises(PlanSuggestionError, match="duplicate"):
        parse_plan_suggestion(raw, plan_id="server-plan-4", registry=CapabilityRegistry([definition()]))


def test_unknown_dependency_and_cycles_are_rejected():
    registry = CapabilityRegistry([definition()])
    step = {
        "step_id": "lookup",
        "capability": "research.lookup",
        "objective": "Search",
        "depends_on": ["missing"],
    }
    with pytest.raises(PlanSuggestionError, match="structural validation"):
        parse_plan_suggestion(
            proposal(steps=[step]), plan_id="server-plan-5", registry=registry
        )


def test_invalid_json_and_oversized_proposals_fail_closed():
    registry = CapabilityRegistry([definition()])
    with pytest.raises(PlanSuggestionError, match="valid JSON"):
        parse_plan_suggestion("{", plan_id="server-plan-6", registry=registry)
    with pytest.raises(PlanSuggestionError, match="bounded JSON"):
        parse_plan_suggestion(" " * 24_001, plan_id="server-plan-7", registry=registry)
