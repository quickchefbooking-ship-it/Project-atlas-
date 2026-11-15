"""Convert untrusted model plan JSON into a trusted, non-executing plan.

The model may propose objectives and dependency structure only. Capability
identity, version, risk, required scopes, timeout and resource budget are
derived from the application-owned registry, never accepted from model output.
"""
from __future__ import annotations

import json
from typing import Any

from .capability_registry import CapabilityRegistry
from .plan_contract import PlanStep, ProfessorPlan, RiskClass

MAX_PLAN_JSON_CHARS = 24_000
MAX_STEPS = 32
MAX_ACCEPTANCE_CRITERIA = 16
MAX_PLAN_ID_CHARS = 128

_RISK_MAP = {
    "read_only": RiskClass.READ_ONLY,
    "local_computation": RiskClass.LOCAL_COMPUTATION,
    "local_write": RiskClass.DRAFT_CREATION,
    "external_write": RiskClass.EXTERNAL_SIDE_EFFECT,
    "privileged": RiskClass.PRIVILEGED,
}


class PlanSuggestionError(ValueError):
    """A proposed plan is malformed or references untrusted capability data."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PlanSuggestionError("Plan JSON contains a duplicate field.")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise PlanSuggestionError("Plan JSON contains a non-finite number.")


def parse_plan_suggestion(
    raw_json: str,
    *,
    plan_id: str,
    registry: CapabilityRegistry,
) -> ProfessorPlan:
    """Validate a model proposal and bind it to trusted capability metadata.

    Expected JSON fields are objective, acceptance_criteria and steps. Each
    step may contain only step_id, capability, objective, depends_on and
    expected_output. Risk, scopes, version and execution budgets are not
    model-controlled.
    """
    if not isinstance(registry, CapabilityRegistry):
        raise TypeError("A trusted application capability registry is required.")
    if not isinstance(plan_id, str) or not plan_id.strip() or len(plan_id) > MAX_PLAN_ID_CHARS:
        raise PlanSuggestionError("A server-generated bounded plan ID is required.")
    if not isinstance(raw_json, str) or not raw_json.strip() or len(raw_json) > MAX_PLAN_JSON_CHARS:
        raise PlanSuggestionError("Plan proposal must be a bounded JSON string.")
    try:
        payload = json.loads(
            raw_json,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except PlanSuggestionError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError):
        raise PlanSuggestionError("Plan proposal is not valid JSON.") from None
    if not isinstance(payload, dict) or set(payload) != {"objective", "acceptance_criteria", "steps"}:
        raise PlanSuggestionError("Plan proposal must contain exactly objective, acceptance_criteria and steps.")

    objective = payload["objective"]
    criteria = payload["acceptance_criteria"]
    raw_steps = payload["steps"]
    if not isinstance(objective, str) or not objective.strip() or len(objective) > 2000:
        raise PlanSuggestionError("Plan objective must contain 1 to 2000 characters.")
    if (
        not isinstance(criteria, list)
        or not 1 <= len(criteria) <= MAX_ACCEPTANCE_CRITERIA
        or any(not isinstance(item, str) or not item.strip() or len(item) > 2000 for item in criteria)
    ):
        raise PlanSuggestionError("Acceptance criteria must be a bounded list of non-empty strings.")
    if not isinstance(raw_steps, list) or not 1 <= len(raw_steps) <= MAX_STEPS:
        raise PlanSuggestionError("Plan must contain between 1 and 32 proposed steps.")

    steps: list[PlanStep] = []
    allowed_step_fields = {"step_id", "capability", "objective", "depends_on", "expected_output"}
    for item in raw_steps:
        if not isinstance(item, dict) or not set(item).issubset(allowed_step_fields):
            raise PlanSuggestionError("A proposed step contains unsupported or privileged fields.")
        if not {"step_id", "capability", "objective"}.issubset(item):
            raise PlanSuggestionError("Each proposed step requires step_id, capability and objective.")
        step_id = item["step_id"]
        capability = item["capability"]
        step_objective = item["objective"]
        if any(not isinstance(value, str) or not value.strip() or len(value) > 2000
               for value in (step_id, capability, step_objective)):
            raise PlanSuggestionError("Step identifiers and objectives must be bounded non-empty strings.")
        definitions = [
            definition for definition in registry.list_definitions()
            if definition.name == capability
        ]
        if len(definitions) != 1:
            raise PlanSuggestionError("Proposed capability is unavailable or has an ambiguous version.")
        definition = definitions[0]
        risk = _RISK_MAP.get(definition.risk_class)
        if risk is None:
            raise PlanSuggestionError("Registered capability risk cannot be represented by the plan contract.")
        dependencies = item.get("depends_on", [])
        if (
            not isinstance(dependencies, list)
            or len(dependencies) > 16
            or any(not isinstance(dep, str) or not dep.strip() for dep in dependencies)
        ):
            raise PlanSuggestionError("Step dependencies must be a bounded list of identifiers.")
        expected_output = item.get("expected_output", "")
        if not isinstance(expected_output, str) or len(expected_output) > 2000:
            raise PlanSuggestionError("Expected output must be a bounded string.")
        steps.append(PlanStep(
            step_id=step_id,
            capability=definition.name,
            objective=step_objective,
            risk=risk,
            depends_on=tuple(dependencies),
            required_scopes=definition.required_scopes,
            expected_output=expected_output,
            timeout_seconds=definition.timeout_seconds,
            resource_budget=1,
            capability_version=definition.version,
        ))

    try:
        return ProfessorPlan(
            plan_id=plan_id,
            objective=objective,
            acceptance_criteria=tuple(criteria),
            steps=tuple(steps),
        )
    except ValueError as exc:
        raise PlanSuggestionError("Proposed plan failed structural validation.") from exc
