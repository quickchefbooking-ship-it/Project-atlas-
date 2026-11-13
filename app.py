import hmac
import json
from contextlib import asynccontextmanager
import os
from typing import Optional, Any

from fastapi import FastAPI, Header, HTTPException, status, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from atlas_engine.config import API_KEY, API_REQUIRE_AUTH
from atlas_engine.task_manager import TaskAPI, TaskInput, ProposalReviewInput, TaskManager
from atlas_engine.executor import LocalTaskExecutor
from atlas_engine.evaluator import Evaluator
from atlas_engine.improvement import ImprovementManager
from atlas_engine.learning_memory import LearningMemory
from atlas_engine.safe_testing import SafeTester
from atlas_engine import storage
from atlas_media.generate import generate_image_from_prompt, generate_video_from_prompt
from atlas_engine.source_division import load_bundled_knowledge, list_sources, retrieve, register_source
from atlas_engine.source_adapters import import_json_batch, MAX_BATCH_JSON_CHARS
import logging

logger = logging.getLogger(__name__)


class StorageBackend:
    now_isoformat = staticmethod(storage.now_isoformat)
    save_task = staticmethod(storage.save_task)
    get_task = staticmethod(storage.get_task)
    list_tasks = staticmethod(storage.list_tasks)
    update_task = staticmethod(storage.update_task)


manager = TaskManager(StorageBackend())
api = TaskAPI(manager, LocalTaskExecutor("local"), Evaluator, LearningMemory(), ImprovementManager(), SafeTester())
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Import repository-owned curated references into the persistent local store."""
    imported = load_bundled_knowledge()
    if storage.get_source("manual-paste") is None:
        register_source("manual-paste", "Manual Research Imports", "manual_paste", access_mode="approval_gated")
    logger.info("Imported %s new curated knowledge documents", imported)
    yield


app = FastAPI(title="AtlasOnePro — Professor Core", lifespan=lifespan)


def require_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    """Fail closed on data-changing and private routes unless explicitly configured for local dev."""
    if not API_REQUIRE_AUTH:
        return True
    expected_key = os.getenv("ATLAS_API_KEY") or API_KEY
    if not expected_key:
        raise HTTPException(status_code=503, detail="API authentication is enabled but ATLAS_API_KEY is not configured")
    if not x_api_key or not hmac.compare_digest(x_api_key, expected_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")
    return True


class SourceImportRequest(BaseModel):
    source_id: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any]


class GenerateImageRequest(BaseModel):
    prompt: str
    output_path: Optional[str] = None


class GenerateVideoRequest(BaseModel):
    prompt: str
    narration: Optional[str] = None
    output_path: Optional[str] = None


@app.get("/professor/sources", include_in_schema=False)
def professor_sources_ui():
    """Serve the static Source Division operator interface; data remains API-key protected."""
    return FileResponse("static/professor_sources.html", media_type="text/html")


@app.get("/health")
def health():
    return api.health()


@app.get("/sources", dependencies=[Depends(require_api_key)])
def list_sources_route():
    """Return registered source descriptors without exposing imported document bodies."""
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "source_type": item["source_type"],
            "access_mode": item["access_mode"],
            "enabled": bool(item["enabled"]),
            "metadata": json.loads(item["metadata_json"]),
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
        }
        for item in list_sources()
    ]


@app.get("/sources/documents", dependencies=[Depends(require_api_key)])
def list_source_documents_route(
    state: Optional[str] = None,
    limit: int = 100,
):
    """List document review metadata; content is available only through approved search."""
    if state is not None and state not in {"pending", "approved", "rejected"}:
        raise HTTPException(status_code=422, detail="State must be pending, approved or rejected")
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 100")
    documents = storage.list_source_documents(limit=limit, state=state)
    return [
        {
            "id": item["id"],
            "source_id": item["source_id"],
            "title": item["title"],
            "uri": item["uri"],
            "content_sha256": item["content_sha256"],
            "trust_level": item["trust_level"],
            "state": item["state"],
            "metadata": json.loads(item["metadata_json"]),
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
            "reviewed_by": item.get("reviewed_by"),
        }
        for item in documents
    ]


@app.post("/sources/import", dependencies=[Depends(require_api_key)])
def import_source_documents(payload: SourceImportRequest):
    """Stage a pasted JSON batch as pending/unverified; never auto-approve it."""
    try:
        serialized = json.dumps(payload.payload, ensure_ascii=False)
        if len(serialized) > MAX_BATCH_JSON_CHARS:
            raise ValueError("JSON batch exceeds the maximum permitted size.")
        staged = import_json_batch(payload.source_id, serialized)
        return {
            "status": "staged_for_review",
            "count": len(staged),
            "documents": [
                {
                    "id": item["id"],
                    "source_id": item["source_id"],
                    "title": item["title"],
                    "uri": item["uri"],
                    "content_sha256": item["content_sha256"],
                    "state": item["state"],
                    "trust_level": item["trust_level"],
                }
                for item in staged
            ],
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/sources/search", dependencies=[Depends(require_api_key)])
def search_source_knowledge(q: str, limit: int = 5):
    """Search approved knowledge only, retaining provenance on every result."""
    if not q.strip() or len(q) > 500:
        raise HTTPException(status_code=422, detail="Query must contain 1 to 500 characters")
    if limit < 1 or limit > 50:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 50")
    return retrieve(q, limit=limit)


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
        raise HTTPException(status_code=422, detail=f"Missing required fields: {', '.join(sorted(missing))}")
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
    return {"status": "ok", "path": generate_image_from_prompt(payload.prompt, payload.output_path)}


@app.post("/media/generate-video", dependencies=[Depends(require_api_key)])
def generate_video(payload: GenerateVideoRequest):
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")
    return {"status": "ok", "path": generate_video_from_prompt(payload.prompt, payload.output_path, payload.narration)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
