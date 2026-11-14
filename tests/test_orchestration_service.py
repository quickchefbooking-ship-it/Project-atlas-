import sqlite3

import pytest

from atlas_engine.capability_registry import CapabilityDefinition, CapabilityRegistry
from atlas_engine.orchestration_service import ProfessorOrchestrationService
from atlas_engine.plan_contract import PlanStep, ProfessorPlan, RiskClass
from atlas_engine.plan_repository import PlanNotFound, PlanRepository


def test_service_previews_a_persisted_plan_without_enabling_execution(tmp_path):
    database = tmp_path / "orchestration-service.db"

    def connect():
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    plans = PlanRepository(connection_factory=connect)
    plan = ProfessorPlan(
        plan_id="service-plan",
        objective="Find public research",
        acceptance_criteria=("Return sourced findings",),
        steps=(
            PlanStep(
                "lookup",
                "knowledge.lookup",
                "Find sources",
                RiskClass.READ_ONLY,
                required_scopes=("knowledge:read",),
                capability_version="1",
            ),
        ),
    )
    plans.create(plan)
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    capabilities = CapabilityRegistry([
        CapabilityDefinition(
            name="knowledge.lookup",
            version="1",
            risk_class="read_only",
            input_schema=schema,
            output_schema=schema,
            required_scopes=("knowledge:read",),
        )
    ])
    service = ProfessorOrchestrationService(
        plans=plans,
        capabilities=capabilities,
    )
    plans.transition(
        "service-plan",
        expected_state=plan.state,
        new_state=plan.mark_ready().state,
    )

    preview = service.preview(
        "service-plan",
        granted_scopes={"knowledge:read"},
    )
    assert preview.plan_id == "service-plan"
    assert preview.structurally_ready_step_ids == ("lookup",)
    assert preview.execution_enabled is False


def test_service_propagates_missing_plan_error(tmp_path):
    database = tmp_path / "orchestration-service.db"

    def connect():
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        return connection

    service = ProfessorOrchestrationService(
        plans=PlanRepository(connection_factory=connect),
        capabilities=CapabilityRegistry(),
    )
    with pytest.raises(PlanNotFound):
        service.preview("does-not-exist")
