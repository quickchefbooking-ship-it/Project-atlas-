import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


class SuccessCriterion(BaseModel):
    field: str
    operator: Literal["==", "!=", "contains", "gt", "gte", "lt", "lte"]
    expected_value: Any
    description: str | None = None
    deterministic: bool = True


class TaskCreate(BaseModel):
    title: str
    description: str
    success_criteria: list[SuccessCriterion] | list[str] | dict[str, Any] = Field(default_factory=list)
    task_type: str = "local_safe_math"
    provider: str | None = "local"


class EvaluationResult(BaseModel):
    passed_: bool = Field(alias="passed")
    score: float
    reasons: list[str]
    missing_requirements: list[str]
    method: Literal["deterministic", "subjective_ai"]
    notes: str = ""


class Evaluator:
    @staticmethod
    def normalize_success_criteria(criteria: Any) -> list[SuccessCriterion]:
        if criteria is None:
            return []
        if isinstance(criteria, dict):
            # dict form can be {"field": "value", "operator": "==", "expected_value": 42}
            if "field" in criteria:
                return [SuccessCriterion(**criteria)]
            # allow {"criteria": [ ... ] }
            if "criteria" in criteria:
                return Evaluator.normalize_success_criteria(criteria["criteria"])
            raise ValueError("Unsupported criteria dictionary format")
        if isinstance(criteria, str):
            return [SuccessCriterion(field="value", operator="==", expected_value=criteria, description="Exact text match", deterministic=True)]
        if isinstance(criteria, list):
            normalized: list[SuccessCriterion] = []
            for item in criteria:
                if isinstance(item, str):
                    normalized.append(
                        SuccessCriterion(
                            field="value",
                            operator="==",
                            expected_value=item,
                            description="Exact text match",
                            deterministic=True,
                        )
                    )
                elif isinstance(item, dict):
                    normalized.append(SuccessCriterion(**item))
                else:
                    raise TypeError(f"Unsupported success criterion item: {type(item)}")
            return normalized
        raise TypeError(f"Unsupported criteria format: {type(criteria)}")

    @staticmethod
    def _compare(field_value: Any, operator: str, expected_value: Any) -> tuple[bool, str]:
        if operator == "==":
            return field_value == expected_value, f"field={field_value} expected={expected_value}"
        if operator == "!=":
            return field_value != expected_value, f"field={field_value} expected not {expected_value}"
        if operator == "contains":
            if not isinstance(field_value, str):
                return False, "field is not a string"
            return expected_value in field_value, f"expected text {expected_value!r} in {field_value!r}"
        if operator == "gt":
            return field_value > expected_value, f"field={field_value} must be > {expected_value}"
        if operator == "gte":
            return field_value >= expected_value, f"field={field_value} must be >= {expected_value}"
        if operator == "lt":
            return field_value < expected_value, f"field={field_value} must be < {expected_value}"
        if operator == "lte":
            return field_value <= expected_value, f"field={field_value} must be <= {expected_value}"
        raise ValueError(f"Unsupported operator: {operator}")

    @classmethod
    def evaluate(cls, result: Any, success_criteria: Any) -> dict[str, Any]:
        criteria = cls.normalize_success_criteria(success_criteria)
        if not criteria:
            return {
                "passed": False,
                "score": 0.0,
                "reasons": ["No success criteria supplied."],
                "missing_requirements": ["Provide measurable success criteria."],
                "method": "deterministic",
            }

        result_obj = result if isinstance(result, dict) else {"value": result}
        reasons: list[str] = []
        missing: list[str] = []
        satisfied = 0

        for criterion in criteria:
            field_value = result_obj.get(criterion.field)
            ok, reason = cls._compare(field_value, criterion.operator, criterion.expected_value)
            if ok:
                satisfied += 1
            else:
                reasons.append(reason)
                missing.append(criterion.description or f"{criterion.field} {criterion.operator} {criterion.expected_value}")

        score = (satisfied / len(criteria)) if criteria else 0.0
        passed = score == 1.0

        return {
            "passed": passed,
            "score": round(score, 4),
            "reasons": reasons,
            "missing_requirements": missing,
            "method": "deterministic",
        }
