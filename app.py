import json
from datetime import datetime, timezone
from typing import Any, Dict

from pydantic import BaseModel, Field

from .config import API_KEY, APP_NAME
from .storage import get_database_status, get_task, list_lessons, list_proposals, list_tasks, save_task


class HealthResponse(BaseModel):
    status: str
    app: str
    database: Dict[str, Any]


class TaskInput(BaseModel):
    title: str
    description: str
    success_criteria: list[dict[str, Any]] | list[str] | dict[str, Any] = Field(default_factory=list)
    provider: str = "local"


class ProposalReviewInput(BaseModel):
    action: str
    approved_by: str


class TaskAPI:
    def __init__(self, manager: Any, executor: Any, evaluator: Any, memory: Any, improvement: Any, safe_tester: Any):
        self.manager = manager
        self.executor = executor
        self.evaluator = evaluator
        self.memory = memory
        self.improvement = improvement
        self.safe_tester = safe_tester

    def require_auth(self, api_key: str | None) -> None:
        configured = os.getenv("ATLAS_API_KEY")
        if configured:
            if not api_key or api_key != configured:
                raise PermissionError("Invalid or missing API key")

    def health(self) -> dict:
        return {
            "status": "ok",
            "app": APP_NAME,
            "database": get_database_status(),
        }

    def create_task(self, payload: TaskInput) -> Dict[str, Any]:
        task = self.manager.create_task(payload.title, payload.description, payload.success_criteria, task_type="local_safe_math")
        return task.model_dump()

    def list_tasks(self, limit: int = 20) -> list[Dict[str, Any]]:
        return [t.model_dump() for t in self.manager.list_tasks(limit)]

    def run_task(self, task_id: str) -> Dict[str, Any]:
        task_row = self.manager.get_task(task_id)
        if task_row is None:
            raise ValueError(f"Task {task_id} not found")

        task_dict = task_row.model_dump()
        execution = self.executor.execute(task_dict)
        evaluation = self.evaluator.evaluate(execution, task_dict["success_criteria"])
        task_dict["attempts"] = (task_dict.get("attempts") or 0) + 1
        task_dict["status"] = "passed" if evaluation["passed"] else "failed"
        task_dict["score"] = evaluation["score"]
        task_dict["result"] = execution
        self.manager.update_status(task_id, task_dict["status"], evaluation["score"], execution)

        if not evaluation["passed"]:
            lesson = self.memory.save_lesson_for_task(
                task_id,
                "mistake",
                f"Task failed with criteria: {evaluation['missing_requirements']}",
                "task_execution",
                {"result": execution, "reasons": evaluation["reasons"]},
                validated=False,
            )
            proposal = self.improvement.create_proposal(
                task_id,
                problem=f"Task did not meet success criteria: {evaluation['missing_requirements']}",
                evidence={"result": execution, "reasons": evaluation["reasons"]},
                proposed_change="Refine task instructions and validation criteria.",
                expected_benefit="Improve reliability and reduce future failures.",
                test_plan="Run minimal pytest checks in isolated temp workspace.",
                created_by="human",
            )
            return {"task_id": task_id, "execution": execution, "evaluation": evaluation, "lesson": lesson, "proposal": proposal}

        self.memory.save_lesson_for_task(
            task_id,
            "success",
            "Task completed and met the criteria on the first validated run.",
            "task_execution",
            {"result": execution, "score": evaluation["score"]},
            validated=True,
        )
        return {"task_id": task_id, "execution": execution, "evaluation": evaluation}

    def get_evaluations(self, task_id: str) -> list[Dict[str, Any]]:
        from .storage import get_evaluations_for_task
        return get_evaluations_for_task(task_id)

    def list_lessons(self, limit: int = 20) -> list[Dict[str, Any]]:
        return list_lessons(limit)

    def list_proposals(self, limit: int = 20) -> list[Dict[str, Any]]:
        return list_proposals(limit)

    def review_proposal(self, proposal_id: str, payload: ProposalReviewInput) -> Dict[str, Any]:
        proposal = self.improvement.review_proposal(proposal_id, payload.action, payload.approved_by)
        if payload.action == "approve":
            gate = self.improvement.check_production_gate(proposal_id)
            return {"proposal": proposal, "production_gate": gate}
        return {"proposal": proposal}

    def dashboard(self) -> Dict[str, Any]:
        tasks = self.manager.list_tasks(50)
        lessons = self.list_lessons(20)
        proposals = self.list_proposals(20)
        passed = sum(1 for task in tasks if task.status == "passed")
        failed = sum(1 for task in tasks if task.status == "failed")
        total = len(tasks)
        return {
            "total_tasks": total,
            "passed_tasks": passed,
            "failed_tasks": failed,
            "pass_rate": round((passed / total) * 100, 2) if total else 0.0,
            "tasks": [task.model_dump() for task in tasks],
            "lessons": lessons,
            "pending_proposals": [p for p in proposals if p["status"] == "pending"],
        }

