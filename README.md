import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Depends, status
from pydantic import BaseModel

from atlas_engine.task_manager import TaskAPI, TaskInput, ProposalReviewInput
from atlas_engine.task_manager import TaskManager
from atlas_engine.executor import LocalTaskExecutor
from atlas_engine.evaluator import Evaluator
from atlas_engine.learning_memory import LearningMemory
from atlas_engine.improvement import ImprovementManager
from atlas_engine.safe_testing import SafeTester
from atlas_engine.storage import get_database_status

app = FastAPI(title="Project Atlas Learning Engine")


manager = TaskManager(storage_backend=None)
# storage_backend compatibility stub for TaskManager

# Lightweight storage shim for the task manager that keeps the data model integrated with the SQLite storage layer.
class StorageBackend:
    def __init__(self):
        pass

    @staticmethod
    def now_isoformat():
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def save_task(task: dict[str, Any]):
        from atlas_engine.storage import save_task
        save_task(task)

    @staticmethod
    def get_task(task_id: str):
        from atlas_engine.storage import get_task
        return get_task(task_id)

    @staticmethod
    def list_tasks(limit: int = 20):
        from atlas_engine.storage import list_tasks
        return list_tasks(limit)

    @staticmethod
    def update_task(task_id: str, updates: dict[str, Any]):
        from atlas_engine.storage import update_task
        update_task(task_id, updates)


manager = TaskManager(StorageBackend())
executor = LocalTaskExecutor("local")
api = TaskAPI(manager, executor, Evaluator, LearningMemory(), ImprovementManager(), SafeTester())


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    configured = os.getenv("ATLAS_API_KEY")
    if configured and (not x_api_key or x_api_key != configured):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")


@app.get("/health")
def health():
    return api.health()


@app.get("/tasks")
def list_tasks():
    return api.list_tasks()


@app.post("/tasks")
def create_task(payload: TaskInput):
    return api.create_task(payload)


@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    task = manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.model_dump()


@app.post("/tasks/{task_id}/run")
def run_task(task_id: str):
    return api.run_task(task_id)


@app.get("/tasks/{task_id}/evaluations")
def get_evaluations(task_id: str):
    return api.get_evaluations(task_id)


@app.get("/lessons")
def list_lessons():
    return api.list_lessons()


@app.post("/proposals")
def create_proposal(payload: dict):
    proposal = api.improvement.create_proposal(
        payload["task_id"],
        payload["problem"],
        payload.get("evidence", {}),
        payload["proposed_change"],
        payload["expected_benefit"],
        payload["test_plan"],
        payload.get("created_by", "human"),
    )
    return proposal


@app.get("/proposals")
def proposals():
    return api.list_proposals()


@app.post("/proposals/{proposal_id}/review")
def review_proposal(proposal_id: str, payload: ProposalReviewInput):
    return api.review_proposal(proposal_id, payload)


@app.get("/dashboard")
def dashboard():
    return api.dashboard()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
