import os
from pathlib import Path
from typing import Optional, Any

from fastapi import FastAPI, Header, HTTPException, status, Depends
from pydantic import BaseModel

from atlas_engine.task_manager import TaskAPI, TaskInput, ProposalReviewInput, TaskManager
from atlas_engine.executor import LocalTaskExecutor
from atlas_engine.evaluator import Evaluator
from atlas_engine.improvement import ImprovementManager
from atlas_engine.learning_memory import LearningMemory
from atlas_engine.safe_testing import SafeTester
from atlas_engine import storage
from atlas_media.generate import generate_image_from_prompt, generate_video_from_prompt, OUTPUT_DIR


class StorageBackend:
    now_isoformat = staticmethod(storage.now_isoformat)
    save_task = staticmethod(storage.save_task)
    get_task = staticmethod(storage.get_task)
    list_tasks = staticmethod(storage.list_tasks)
    update_task = staticmethod(storage.update_task)


manager = TaskManager(StorageBackend())
api = TaskAPI(manager, LocalTaskExecutor("local"), Evaluator, LearningMemory(), ImprovementManager(), SafeTester())
app = FastAPI(title="AtlasOnePro — Professor Core")

# Public health checks are intentionally unauthenticated. All operational routes fail closed.
REQUIRE_AUTH = os.getenv("ATLAS_API_REQUIRE_AUTH", "true").lower() == "true"
ATLAS_API_KEY = os.getenv("ATLAS_API_KEY")


def require_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    if not REQUIRE_AUTH:
        return True
    if not ATLAS_API_KEY:
        raise HTTPException(status_code=503, detail="API authentication is enabled but ATLAS_API_KEY is not configured")
    if x_api_key != ATLAS_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")
    return True


def validate_output_path(requested_path: Optional[str]) -> Optional[str]:
    if requested_path is None:
        return None
    candidate = Path(requested_path).expanduser()
    base = Path(OUTPUT_DIR).resolve()
    resolved = (base / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Output path must stay inside the configured media output directory") from exc
    return str(resolved)


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


@app.get("/tasks", dependencies=[Depends(require_api_key)])
def list_tasks_route():
    return api.list_tasks()


@app.post("/tasks", dependencies=[Depends(require_api_key)])
def create_task(payload: TaskInput):
    return api.create_task(payload)


@app.get("/tasks/{task_id}", dependencies=[Depends(require_api_key)])
def get_task_route(task_id: str):
    task = manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.model_dump()


@app.post("/tasks/{task_id}/run", dependencies=[Depends(require_api_key)])
def run_task(task_id: str):
    result = api.run_task(task_id)
    if result.get("error") == "Task not found":
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@app.get("/tasks/{task_id}/evaluations", dependencies=[Depends(require_api_key)])
def get_evaluations(task_id: str):
    return api.get_evaluations(task_id)


@app.get("/lessons", dependencies=[Depends(require_api_key)])
def list_lessons_route():
    return api.list_lessons()


@app.post("/proposals", dependencies=[Depends(require_api_key)])
def create_proposal(payload: dict[str, Any]):
    required = {"task_id", "problem", "proposed_change", "expected_benefit", "test_plan"}
    missing = required - payload.keys()
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing proposal fields: {', '.join(sorted(missing))}")
    return api.improvement.create_proposal(
        payload["task_id"], payload["problem"], payload.get("evidence", {}),
        payload["proposed_change"], payload["expected_benefit"], payload["test_plan"],
        payload.get("created_by", "human"))


@app.get("/proposals", dependencies=[Depends(require_api_key)])
def proposals():
    return api.list_proposals()


@app.post("/proposals/{proposal_id}/review", dependencies=[Depends(require_api_key)])
def review_proposal(proposal_id: str, payload: ProposalReviewInput):
    return api.review_proposal(proposal_id, payload)


@app.get("/dashboard", dependencies=[Depends(require_api_key)])
def dashboard():
    return api.dashboard()


@app.get("/media/health")
def media_health():
    return {"status": "ok", "media": "Atlas media generation enabled"}


@app.post("/media/generate-image", dependencies=[Depends(require_api_key)])
def generate_image(payload: GenerateImageRequest):
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")
    output_path = validate_output_path(payload.output_path)
    return {"status": "ok", "path": generate_image_from_prompt(payload.prompt, output_path)}


@app.post("/media/generate-video", dependencies=[Depends(require_api_key)])
def generate_video(payload: GenerateVideoRequest):
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")
    output_path = validate_output_path(payload.output_path)
    return {"status": "ok", "path": generate_video_from_prompt(payload.prompt, output_path, payload.narration)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
