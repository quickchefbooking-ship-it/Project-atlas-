import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class TaskInput(BaseModel):
    title: str
    description: str
    success_criteria: list[dict[str, Any]] | list[str] | dict[str, Any] = Field(default_factory=list)

class ProposalReviewInput(BaseModel):
    action: str
    approved_by: str

class Task(BaseModel):
    id: str
    title: str
    description: str
    success_criteria: Any = Field(default_factory=list)
    status: str = "pending"
    attempts: int = 0
    score: float = 0.0
    result: dict[str, Any] | None = None
    created_at: str
    updated_at: str

class TaskManager:
    def __init__(self, storage_backend: Any):
        self.storage_backend = storage_backend

    def create_task(self, title: str, description: str, success_criteria: Any) -> Task:
        if not title.strip() or not description.strip():
            raise ValueError("Task title and description are required.")
        now = self.storage_backend.now_isoformat()
        criteria = success_criteria if success_criteria is not None else []
        task_id = f"task-{os.urandom(12).hex()}"
        row = {
            "id": task_id, "title": title, "description": description,
            "success_criteria_json": json.dumps(criteria), "status": "pending",
            "attempts": 0, "score": 0.0, "result_json": None,
            "created_at": now, "updated_at": now,
        }
        self.storage_backend.save_task(row)
        return Task(id=task_id, title=title, description=description,
                    success_criteria=criteria, created_at=now, updated_at=now)

    def get_task(self, task_id: str) -> Task | None:
        row = self.storage_backend.get_task(task_id)
        if row is None:
            return None
        return Task(
            id=row["id"], title=row["title"], description=row["description"],
            success_criteria=json.loads(row["success_criteria_json"]),
            status=row["status"], attempts=row["attempts"], score=row["score"],
            result=json.loads(row["result_json"]) if row.get("result_json") else None,
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def list_tasks(self, limit: int = 20) -> list[Task]:
        rows = self.storage_backend.list_tasks(limit)
        return [self.get_task(row["id"]) for row in rows]

    def claim_task(self, task_id: str) -> bool:
        """Claim a pending task using the storage backend's atomic compare-and-set."""
        return self.storage_backend.claim_task(task_id)

    def update_status(self, task_id: str, status: str, score: float | None = None,
                      result: dict[str, Any] | None = None,
                      increment_attempt: bool = False) -> Task | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        updates: dict[str, Any] = {"status": status, "updated_at": self.storage_backend.now_isoformat()}
        if score is not None:
            updates["score"] = score
        if result is not None:
            updates["result_json"] = json.dumps(result, sort_keys=True)
        if increment_attempt:
            updates["attempts"] = task.attempts + 1
        self.storage_backend.update_task(task_id, updates)
        return self.get_task(task_id)

class TaskAPI:
    def __init__(self, manager, executor, evaluator, memory, improvement, tester):
        self.manager, self.executor, self.evaluator = manager, executor, evaluator
        self.memory, self.improvement, self.tester = memory, improvement, tester

    def health(self):
        return {"status": "ok", "service": "AtlasOnePro Professor Core"}

    def create_task(self, payload: TaskInput):
        return self.manager.create_task(payload.title, payload.description, payload.success_criteria).model_dump()

    def list_tasks(self):
        return [task.model_dump() for task in self.manager.list_tasks()]

    def run_task(self, task_id: str):
        task = self.manager.get_task(task_id)
        if task is None:
            return {"error": "Task not found"}
        if not self.manager.claim_task(task_id):
            current = self.manager.get_task(task_id)
            return {
                "task_id": task_id,
                "status": current.status if current is not None else "unavailable",
                "error": "Task is already running or is not pending.",
            }
        # Reload after the atomic claim so the executor sees the persisted attempt count.
        task = self.manager.get_task(task_id)
        if task is None:
            return {"task_id": task_id, "status": "unavailable", "error": "Task is unavailable."}
        try:
            # Retrieve only validated lessons; pass them as context to capable executors.
            # The restricted local arithmetic executor deliberately ignores this context.
            relevant_lessons = self.memory.get_relevant_lessons(task.description) if hasattr(
                self.memory, "get_relevant_lessons"
            ) else []
            try:
                from .source_division import retrieve as retrieve_sources
                source_documents = retrieve_sources(task.description)
            except Exception as source_error:
                logger.warning(
                    "Source Division retrieval unavailable for task_id=%s error_type=%s",
                    task_id,
                    type(source_error).__name__,
                )
                source_documents = []
            result = self.executor.execute({
                "title": task.title,
                "description": task.description,
                "relevant_lessons": relevant_lessons,
                "source_documents": source_documents,
            })
            evaluation = self.evaluator.evaluate(result, task.success_criteria)
            status = "passed" if evaluation["passed"] else "failed"

            # Commit the terminal task state and its evaluation together. A partial
            # write must never leave a terminal task without its audit record.
            from .storage import complete_task_with_evaluation
            evaluation_record = {
                "id": f"evaluation-{os.urandom(12).hex()}",
                "task_id": task_id,
                "passed": evaluation["passed"],
                "score": evaluation["score"],
                "reasons_json": json.dumps(evaluation["reasons"], sort_keys=True),
                "missing_requirements_json": json.dumps(evaluation["missing_requirements"], sort_keys=True),
                "method": evaluation["method"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            if not complete_task_with_evaluation(task_id, evaluation_record, status, result):
                current = self.manager.get_task(task_id)
                return {
                    "task_id": task_id,
                    "status": current.status if current is not None else "unavailable",
                    "error": "Task completion was not committed because the task is no longer running.",
                }

            if not evaluation["passed"]:
                try:
                    self.memory.save_lesson_for_task(
                        task_id,
                        "failure",
                        "Task failed its success criteria.",
                        "deterministic-evaluation",
                        {"evaluation": evaluation},
                        validated=False,
                    )
                except Exception as lesson_error:
                    # Learning-record failure must not rewrite an already committed
                    # task outcome or hide its persisted evaluation from the caller.
                    logger.warning(
                        "Failure lesson persistence unavailable for task_id=%s error_type=%s",
                        task_id,
                        type(lesson_error).__name__,
                    )
            return {"task_id": task_id, "status": status, "result": result, "evaluation": evaluation}
        except Exception as exc:
            self.manager.update_status(task_id, "failed")
            # Keep exception messages out of API responses and logs: they can contain
            # credentials, file paths or private task data. Record only the error type.
            logger.error(
                "Task execution failed for task_id=%s error_type=%s",
                task_id,
                type(exc).__name__,
            )
            return {
                "task_id": task_id,
                "status": "failed",
                "error": "Task execution failed. Check the server diagnostics using the task ID.",
            }

    def get_evaluations(self, task_id: str):
        from .storage import get_evaluations_for_task
        return get_evaluations_for_task(task_id)

    def list_lessons(self):
        from .storage import list_lessons
        return list_lessons()

    def list_proposals(self):
        return self.improvement.list_proposals()

    def review_proposal(self, proposal_id: str, payload: ProposalReviewInput):
        return self.improvement.review_proposal(proposal_id, payload.action, payload.approved_by)

    def dashboard(self):
        return {"tasks": self.list_tasks(), "lessons": self.list_lessons(),
                "proposals": self.list_proposals()}
