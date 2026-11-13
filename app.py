import hmac
import json
from contextlib import asynccontextmanager
import os
from pathlib import Path
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
from atlas_engine.source_adapters import import_json_batch, stage_adapter_results, MAX_BATCH_JSON_CHARS
from atlas_engine.public_research_adapters import fetch_github_repository, fetch_huggingface_resource, search_uk_legislation, search_crossref_works, PublicSourceError
import logging
from atlas_engine.public_web_retrieval import fetch_public_web_page

logger = logging.getLogger(__name__)


class StorageBackend:
    now_isoformat = staticmethod(storage.now_isoformat)
    save_task = staticmethod(storage.save_task)
    get_task = staticmethod(storage.get_task)
    list_tasks = staticmethod(storage.list_tasks)
    update_task = staticmethod(storage.update_task)
    claim_task = staticmethod(storage.claim_task)
    claim_task_with_lease = staticmethod(storage.claim_task_with_lease)
    heartbeat_task_attempt = staticmethod(storage.heartbeat_task_attempt)
    complete_task_with_evaluation = staticmethod(storage.complete_task_with_evaluation)


manager = TaskManager(StorageBackend())
api = TaskAPI(manager, LocalTaskExecutor("local"), Evaluator, LearningMemory(), ImprovementManager(), SafeTester())
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Import repository-owned curated references into the persistent local store."""
    imported = load_bundled_knowledge()
    if storage.get_source("manual-paste") is None:
        register_source("manual-paste", "Manual Research Imports", "manual_paste", access_mode="approval_gated")
    if storage.get_source("github-public") is None:
        register_source("github-public", "GitHub Public Repositories", "github_public_api", access_mode="read_only", metadata={"endpoint": "api.github.com", "scope": "public repository metadata only"})
    if storage.get_source("huggingface-public") is None:
        register_source("huggingface-public", "Hugging Face Public Resources", "huggingface_public_api", access_mode="read_only", metadata={"endpoint": "huggingface.co/api", "scope": "public model and dataset metadata only"})
    if storage.get_source("uk-legislation") is None:
        register_source("uk-legislation", "UK Legislation — The National Archives", "legislation_gov_uk_api", access_mode="read_only", metadata={"endpoint": "www.legislation.gov.uk", "scope": "official public legislation search and XML text"})
    if storage.get_source("crossref-public") is None:
        register_source("crossref-public", "Crossref Scholarly Metadata", "crossref_public_api", access_mode="read_only", metadata={"endpoint": "api.crossref.org", "scope": "public bibliographic metadata and abstracts when supplied"})
    if storage.get_source("public-web") is None:
        register_source("public-web", "Allowlisted Public Web Pages", "allowlisted_public_web", access_mode="read_only", metadata={"scope": "approved public HTTPS hosts; HTML/plain text only; pending review"})
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


class PublicSourceFetchRequest(BaseModel):
    provider: str = Field(pattern="^(github|huggingface|legislation|crossref)$")
    identifier: str = Field(min_length=1, max_length=201)
    resource_type: str = Field(default="repository", pattern="^(repository|model|dataset|ukpga|uksi|asp|anaw|nia|nisr|ukla|scholarly_work)$")


class PublicWebFetchRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)

class TaskRecoveryDecisionInput(BaseModel):
    attempt_id: str = Field(min_length=1, max_length=128)
    action: str = Field(pattern="^(mark_failed|retry)$")
    actor: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=500)
    retry_safe: bool = False
    side_effects_reconciled: bool = False


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
    return FileResponse(Path(__file__).resolve().parent / "static" / "professor_sources.html", media_type="text/html")


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


class _SingleDocumentAdapter:
    def __init__(self, source_id: str, documents):
        self.source_id = source_id
        self.documents = documents if isinstance(documents, list) else [documents]

    def search(self, query: str, limit: int = 10):
        return self.documents[:limit]


@app.post("/sources/fetch", dependencies=[Depends(require_api_key)])
def fetch_public_source(payload: PublicSourceFetchRequest):
    """Fetch bounded public metadata from a fixed provider API and stage it for review."""
    try:
        if payload.provider == "github":
            if payload.resource_type != "repository":
                raise HTTPException(status_code=422, detail="GitHub currently supports repository metadata only")
            adapter = _SingleDocumentAdapter("github-public", fetch_github_repository(payload.identifier))
        elif payload.provider == "huggingface":
            if payload.resource_type not in {"model", "dataset"}:
                raise HTTPException(status_code=422, detail="Hugging Face supports model or dataset metadata")
            adapter = _SingleDocumentAdapter(
                "huggingface-public",
                fetch_huggingface_resource(payload.identifier, payload.resource_type),
            )
        elif payload.provider == "legislation":
            if payload.resource_type not in {"ukpga", "uksi", "asp", "anaw", "nia", "nisr", "ukla"}:
                raise HTTPException(status_code=422, detail="Choose a supported UK legislation type")
            adapter = _SingleDocumentAdapter(
                "uk-legislation",
                search_uk_legislation(payload.identifier, payload.resource_type, limit=5),
            )
        else:
            if payload.resource_type != "scholarly_work":
                raise HTTPException(status_code=422, detail="Crossref supports scholarly_work searches")
            adapter = _SingleDocumentAdapter(
                "crossref-public",
                search_crossref_works(payload.identifier, limit=5),
            )
        staged = stage_adapter_results(adapter, payload.identifier, limit=5)
        if not staged:
            raise HTTPException(status_code=404, detail="No matching public resources were found.")
        return {
            "status": "staged_for_review",
            "provider": payload.provider,
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
    except PublicSourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/sources/fetch-url", dependencies=[Depends(require_api_key)])
def fetch_public_web_url(payload: PublicWebFetchRequest):
    """Fetch one allowlisted public web page and stage it as untrusted pending material."""
    try:
        adapter = _SingleDocumentAdapter("public-web", fetch_public_web_page(payload.url))
        staged = stage_adapter_results(adapter, payload.url, limit=1)
        return {
            "status": "staged_for_review",
            "provider": "public_web",
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
    except PublicSourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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


@app.post("/tasks/recovery/scan", dependencies=[Depends(require_api_key)])
def scan_task_recovery_route():
    """Mark expired worker leases for operator review; never retry them automatically."""
    marked = storage.mark_expired_task_attempts()
    return {"status": "scan_complete", "marked_for_recovery": marked}


@app.get("/tasks/recovery-required", dependencies=[Depends(require_api_key)])
def list_task_recovery_route():
    """List tasks held for recovery without exposing task results or secrets."""
    return storage.list_recovery_required_attempts()


@app.get("/tasks/{task_id}/attempts", dependencies=[Depends(require_api_key)])
def list_task_attempts_route(task_id: str):
    if manager.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return storage.get_task_attempts(task_id)


@app.post("/tasks/{task_id}/recovery-decision", dependencies=[Depends(require_api_key)])
def resolve_task_recovery_route(task_id: str, payload: TaskRecoveryDecisionInput):
    if manager.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        recorded = storage.resolve_task_recovery(
            task_id, payload.attempt_id,
            payload.action, payload.actor, payload.reason,
            retry_safe=payload.retry_safe,
            side_effects_reconciled=payload.side_effects_reconciled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not recorded:
        raise HTTPException(status_code=409, detail="The attempt is not awaiting recovery or has already been resolved.")
    return {
        "status": "recovery_decision_recorded",
        "task": manager.get_task(task_id).model_dump(),
        "decisions": storage.list_task_recovery_decisions(task_id),
    }


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
