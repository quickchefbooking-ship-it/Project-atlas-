import os
import json
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class Task(BaseModel):
    id: str
    title: str
    description: str
    success_criteria: list[dict[str, Any]] | list[str] | dict[str, Any] = Field(default_factory=list)
    status: str = "pending"
    attempts: int = 0
    score: float = 0.0
    result: dict[str, Any] | None = None
    created_at: str
    updated_at: str


class TaskState(BaseModel):
    task_id: str
    status: str
    attempts: int
    score: float
    result: dict[str, Any] | None = None


class TaskManager:
    def __init__(self, storage_backend: Any):
        self.storage_backend = storage_backend

    def create_task(self, title: str, description: str, success_criteria: Any, task_type: str = "local_safe_math") -> Task:
        if not title.strip():
            raise ValueError("Task title is required.")
        if not description.strip():
            raise ValueError("Task description is required.")
        task = Task(
            id=f"task-{abs(hash(title + description + os.urandom(4).hex()))}",
            title=title,
            description=description,
            success_criteria=success_criteria,
            status="pending",
            attempts=0,
            score=0.0,
            result=None,
            created_at=self.storage_backend.now_isoformat(),
            updated_at=self.storage_backend.now_isoformat(),
        )
        self.storage_backend.save_task(task.model_dump())
        return task

    def get_task(self, task_id: str) -> Task | None:
        row = self.storage_backend.get_task(task_id)
        if row is None:
            return None
        return Task(**row)

    def list_tasks(self, limit: int = 20) -> list[Task]:
        rows = self.storage_backend.list_tasks(limit)
        return [Task(**row) for row in rows]

    def update_status(self, task_id: str, status: str, score: float | None = None, result: dict[str, Any] | None = None) -> Task | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        task.status = status
        task.score = score if score is not None else task.score
        if result is not None:
            task.result = result
        task.updated_at = self.storage_backend.now_isoformat()
        self.storage_backend.update_task(task_id, {
            "status": task.status,
            "score": task.score,
            "result_json": json.dumps(task.result, sort_keys=True) if task.result is not None else None,
            "updated_at": task.updated_at,
        })
        return task
