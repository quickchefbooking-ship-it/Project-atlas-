import os
from typing import Optional, Any

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel

from atlas_engine.task_manager import TaskAPI, TaskInput, ProposalReviewInput, TaskManager
from atlas_engine.executor import LocalTaskExecutor
from atlas_engine.evaluator import Evaluator
from atlas_engine.improvement import ImprovementManager
from atlas_engine.learning_memory import LearningMemory
from atlas_engine.safe_testing import SafeTester
from atlas_engine import storage
from atlas_media.generate import generate_image_from_prompt, generate_video_from_prompt


class StorageBackend:
    now_isoformat = staticmethod(lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat())
    save_task = staticmethod(storage.save_task)
    get_task = staticmethod(storage.get_task)
    list_tasks = staticmethod(storage.list_tasks)
    update_task = staticmethod(storage.update_task)


manager = TaskManager(StorageBackend())
api = TaskAPI(manager, LocalTaskExecutor("local"), Evaluator, LearningMemory(), ImprovementManager(), SafeTester())
app = FastAPI(title="AtlasOnePro — Professor Core")

REQUIRE_AUTH = os.getenv("ATLAS_MEDIA_REQUIRE_AUTH", "false").lower() == "true"
ATLAS_API_KEY = os.getenv("ATLAS_API_KEY")


def require_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    if not REQUIRE_AUTH:
        return True
    if not ATLAS_API_KEY:
        raise HTTPException(status_code=500, detail="ATLAS_API_KEY is not configured")
    if x_api_key != ATLAS_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")
    return True


class GenerateImageRequest(BaseModel):
    prompt: str
    output_path: Optional[str] = None


class GenerateVideoRequest(BaseModel):
    prompt: str
    narration: Optional[str] = None
    output_path: Optional[str] = None


@app.get("/health")
def health():
    return api.health()


@app.get("/tasks")
def list_tasks_route():
    return api.list_tasks()


@app.post("/tasks")
def create_task(payload: TaskInput):
    return api.create_task(payload)


@app.get("/tasks/{task_id}")
def get_task_route(task_id: str):
    task = manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.model_dump()


@app.post("/tasks/{task_id}/run")
def run_task(task_id: str):
    result = api.run_task(task_id)
    if result.get("error") == "Task not found":
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@app.get("/tasks/{task_id}/evaluations")
def get_evaluations(task_id: str):
    return api.get_evaluations(task_id)


@app.get("/lessons")
def list_lessons_route():
    return api.list_lessons()


@app.post("/proposals")
def create_proposal(payload: dict[str, Any]):
    return api.improvement.create_proposal(
        payload["task_id"], payload["problem"], payload.get("evidence", {}),
        payload["proposed_change"], payload["expected_benefit"], payload["test_plan"],
        payload.get("created_by", "human"))


@app.get("/proposals")
def proposals():
    return api.list_proposals()


@app.post("/proposals/{proposal_id}/review")
def review_proposal(proposal_id: str, payload: ProposalReviewInput):
    return api.review_proposal(proposal_id, payload)


@app.get("/dashboard")
def dashboard():
    return api.dashboard()


@app.get("/media/health")
def media_health():
    return {"status": "ok", "media": "Atlas media generation enabled"}


@app.post("/media/generate-image")
def generate_image(payload: GenerateImageRequest, x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    require_api_key(x_api_key)
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")
    return {"status": "ok", "path": generate_image_from_prompt(payload.prompt, payload.output_path)}


@app.post("/media/generate-video")
def generate_video(payload: GenerateVideoRequest, x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    require_api_key(x_api_key)
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")
    return {"status": "ok", "path": generate_video_from_prompt(payload.prompt, payload.output_path, payload.narration)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
