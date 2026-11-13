"""Versioned, bounded research-plan contracts for Professor.

These schemas describe work; they do not execute capabilities. Execution must pass
through a separately authorised capability registry and orchestrator.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PLAN_SCHEMA_VERSION = "1.0"
MAX_PLAN_STEPS = 12
MAX_PLAN_BUDGET_SECONDS = 600
MAX_PLAN_CAPABILITY_CALLS = 20


class ResearchStep(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    step_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    objective: str = Field(min_length=1, max_length=500)
    capability_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$")
    capability_version: str = Field(min_length=1, max_length=64)
    rationale: str = Field(min_length=1, max_length=500)
    expected_evidence: str = Field(min_length=1, max_length=500)
    depends_on: list[str] = Field(default_factory=list, max_length=MAX_PLAN_STEPS)

    @field_validator("depends_on")
    @classmethod
    def no_duplicate_dependencies(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Research step dependencies must be unique.")
        return value


class ResearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["1.0"] = PLAN_SCHEMA_VERSION
    task_id: str = Field(min_length=1, max_length=128)
    objective: str = Field(min_length=1, max_length=2_000)
    scope: str = Field(min_length=1, max_length=2_000)
    exclusions: list[str] = Field(default_factory=list, max_length=30)
    success_criteria: list[str] = Field(min_length=1, max_length=20)
    risk_class: Literal["low", "moderate", "high", "prohibited"]
    max_duration_seconds: int = Field(ge=1, le=MAX_PLAN_BUDGET_SECONDS)
    max_capability_calls: int = Field(ge=1, le=MAX_PLAN_CAPABILITY_CALLS)
    steps: list[ResearchStep] = Field(min_length=1, max_length=MAX_PLAN_STEPS)

    @model_validator(mode="after")
    def validate_plan_graph(self):
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Research step IDs must be unique.")
        known = set(step_ids)
        for step in self.steps:
            missing = set(step.depends_on) - known
            if missing:
                raise ValueError("Research step dependency refers to an unknown step.")
            if step.step_id in step.depends_on:
                raise ValueError("A research step cannot depend on itself.")
        graph = {step.step_id: step.depends_on for step in self.steps}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise ValueError("Research plan contains a dependency cycle.")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in step_ids:
            visit(node)
        if len(self.steps) > self.max_capability_calls:
            raise ValueError("Plan has more steps than its capability-call budget.")
        if self.risk_class in {"high", "prohibited"}:
            raise ValueError("This research-test orchestrator accepts low or moderate risk only.")
        return self
