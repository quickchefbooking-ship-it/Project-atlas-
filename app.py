import hmac
import json
from contextlib import asynccontextmanager
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Optional, Any

from fastapi import FastAPI, Header, HTTPException, status, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
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
from atlas_engine.http_identity import VerifiedIdentityService, require_verified_principal
from atlas_engine.oidc_contract import OIDCProviderConfig
from atlas_engine.oidc_jwt_verifier import PyJWTTokenVerifier
from atlas_engine.tenant_membership import SQLiteMembershipRegistry
from atlas_engine.identity_policy import AuthorizationDenied
from atlas_engine.capability_registry import CapabilityRegistry
from atlas_engine.capability_runtime import build_default_capability_runtime
from atlas_engine.tenant_plan_execution import router as tenant_plan_execution_router
from atlas_engine.tenant_plan_repository import TenantPlanRepository, TenantPlanNotFound, initialize_tenant_plan_schema
from atlas_engine.tenant_step_execution_repository import TenantStepExecutionRepository, TenantStepNotFound, initialize_tenant_step_schema
from atlas_engine.tenant_orchestration_service import TenantProfessorOrchestrationService
from atlas_engine.plan_contract import PlanStep, ProfessorPlan, RiskClass, PlanValidationError
from atlas_engine.tenant_plan_lifecycle import router as tenant_plan_lifecycle_router
from atlas_engine.conversation_service import ConversationService
from atlas_engine.openai_compatible_provider import (
    OpenAICompatibleConversationProvider,
    load_provider_from_environment,
)
from atlas_engine.tenant_conversation_repository import initialize_tenant_conversation_schema
from atlas_engine.tenant_professor_memory import initialize_tenant_memory_schema
from atlas_engine.professor_memory_api import router as professor_memory_router
from atlas_engine.tenant_evaluation_repository import initialize_tenant_evaluation_schema
from atlas_engine.tenant_reasoning_audit import initialize_reasoning_audit_schema
from atlas_engine.professor_reasoning_audit_api import router as professor_reasoning_audit_router
from atlas_engine.professor_evaluation_api import router as professor_evaluation_router
from atlas_engine.tenant_lesson_review import initialize_tenant_lesson_review_schema
from atlas_engine.professor_lesson_review_api import router as professor_lesson_review_router
from atlas_engine.professor_conversation_api import router as professor_conversation_router
from atlas_engine.professor_plan_suggestion_api import router as professor_plan_suggestion_router
from atlas_engine.tenant_approved_sources import initialize_tenant_approved_source_schema
from atlas_engine.tenant_source_assessments import initialize_tenant_source_assessment_schema
from atlas_engine.tenant_source_assessments_api import router as tenant_source_assessments_router
from atlas_engine.tenant_approved_sources_api import router as tenant_approved_sources_router
from atlas_engine.tenant_evidence_review import (
    router as tenant_evidence_review_router,
    initialize_tenant_evidence_review_schema,
)

logger = logging.getLogger(__name__)


def _capability_execution_enabled_from_environment() -> bool:
    """Execution is opt-in: only an explicit true value opens the global gate."""
    return os.getenv("ATLAS_CAPABILITY_EXECUTION_ENABLED", "").strip().lower() == "true"


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
    get_task_cancellation = staticmethod(storage.get_task_cancellation)
    acknowledge_task_cancellation = staticmethod(storage.acknowledge_task_cancellation)


manager = TaskManager(StorageBackend())
api = TaskAPI(manager, LocalTaskExecutor("local"), Evaluator, LearningMemory(), ImprovementManager(), SafeTester())
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Import repository-owned curated references into the persistent local store."""
    app.state.capability_execution_enabled = _capability_execution_enabled_from_environment()
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
    try:
        identity_service = _identity_service_from_environment()
        app.state.identity_service = identity_service
        if identity_service is not None:
            logger.info("Verified identity boundary configured from deployment settings")
    except Exception:
        app.state.identity_service = None
        logger.error("OIDC identity configuration is invalid; verified identity remains disabled")
    try:
        app.state.tenant_data_path = _initialize_tenant_data_store()
    except Exception:
        app.state.tenant_data_path = None
        logger.error("Tenant plan storage initialization failed; tenant plan routes remain disabled")
    app.state.conversation_provider = None
    app.state.conversation_service = ConversationService()
    try:
        provider_config = load_provider_from_environment()
        if provider_config is not None:
            provider = OpenAICompatibleConversationProvider(provider_config)
            app.state.conversation_provider = provider
            app.state.conversation_service = ConversationService(provider)
            logger.info("Professor text reasoning provider configured")
    except Exception:
        logger.error("Professor reasoning provider configuration is invalid; conversation remains disabled")
    yield
    provider = getattr(app.state, "conversation_provider", None)
    if provider is not None:
        provider.close()


app = FastAPI(title="AtlasOnePro — Professor Core", lifespan=lifespan)
app.state.identity_service = None
app.state.tenant_data_path = None
app.state.capability_execution_enabled = _capability_execution_enabled_from_environment()
app.state.tenant_capability_runtime = build_default_capability_runtime()
app.state.tenant_capability_registry = app.state.tenant_capability_runtime.registry
app.include_router(tenant_plan_lifecycle_router)
app.include_router(tenant_plan_execution_router)
app.include_router(tenant_evidence_review_router)
app.include_router(tenant_approved_sources_router)
app.include_router(tenant_source_assessments_router)
app.include_router(professor_conversation_router)
app.include_router(professor_memory_router)
app.include_router(professor_reasoning_audit_router)
app.include_router(professor_evaluation_router)
app.include_router(professor_lesson_review_router)
app.include_router(professor_plan_suggestion_router)
app.state.conversation_service = ConversationService()
app.state.conversation_provider = None


class TenantPlanStepInput(BaseModel):
    model_config = {"extra": "forbid"}
    step_id: str = Field(min_length=1, max_length=2000)
    capability: str = Field(min_length=1, max_length=2000)
    objective: str = Field(min_length=1, max_length=2000)
    risk: RiskClass
    depends_on: list[str] = Field(default_factory=list, max_length=16)
    required_scopes: list[str] = Field(default_factory=list, max_length=64)
    expected_output: str = Field(default="", max_length=2000)
    timeout_seconds: int = Field(default=30, ge=1, le=900)
    resource_budget: int = Field(default=1, ge=1, le=100)
    capability_version: Optional[str] = Field(default=None, min_length=1, max_length=64)


class TenantPlanCreateInput(BaseModel):
    model_config = {"extra": "forbid"}
    objective: str = Field(min_length=1, max_length=2000)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=64)
    steps: list[TenantPlanStepInput] = Field(min_length=1, max_length=64)


def _initialize_tenant_data_store() -> Optional[str]:
    """Initialize only the isolated tenant-plan prototype database."""
    database_path = os.getenv("ATLAS_TENANT_DATA_DB_PATH")
    if not database_path:
        return None
    membership_path = os.getenv("ATLAS_MEMBERSHIP_DB_PATH")
    protected_paths = [getattr(storage, "DB_PATH", None), membership_path]
    tenant_real_path = os.path.realpath(database_path)
    if any(
        path and tenant_real_path == os.path.realpath(path)
        for path in protected_paths
    ):
        raise ValueError(
            "Tenant plan data must use a database separate from core and membership storage."
        )
    connection = sqlite3.connect(database_path, timeout=5)
    try:
        connection.row_factory = sqlite3.Row
        initialize_tenant_plan_schema(connection)
        initialize_tenant_step_schema(connection)
        initialize_tenant_evidence_review_schema(connection)
        initialize_tenant_approved_source_schema(connection)
        initialize_tenant_source_assessment_schema(connection)
        initialize_tenant_conversation_schema(connection)
        initialize_tenant_evaluation_schema(connection)
        initialize_reasoning_audit_schema(connection)
        initialize_tenant_lesson_review_schema(connection)
        initialize_tenant_memory_schema(connection)
        connection.commit()
    finally:
        connection.close()
    return os.path.abspath(database_path)


def _identity_service_from_environment() -> Optional[VerifiedIdentityService]:
    """Build the verifier only from complete deployment-owned OIDC settings."""
    required = (
        "ATLAS_OIDC_ISSUER",
        "ATLAS_OIDC_AUDIENCE",
        "ATLAS_OIDC_JWKS_URI",
        "ATLAS_OIDC_ALLOWED_ALGORITHMS",
        "ATLAS_MEMBERSHIP_DB_PATH",
    )
    values = {name: os.getenv(name) for name in required}
    if not all(values.values()):
        return None
    algorithms = frozenset(
        item.strip() for item in values["ATLAS_OIDC_ALLOWED_ALGORITHMS"].split(",")
        if item.strip()
    )
    config = OIDCProviderConfig(
        issuer=values["ATLAS_OIDC_ISSUER"],
        audience=values["ATLAS_OIDC_AUDIENCE"],
        jwks_uri=values["ATLAS_OIDC_JWKS_URI"],
        allowed_algorithms=algorithms,
    )
    memberships = SQLiteMembershipRegistry(values["ATLAS_MEMBERSHIP_DB_PATH"])
    memberships.initialize()
    return VerifiedIdentityService(
        config=config,
        verifier=PyJWTTokenVerifier(config),
        memberships=memberships,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request, exc: RequestValidationError):
    """Return safe, serializable validation details without echoing request values."""
    details = [
        {
            "loc": list(error.get("loc", ())),
            "msg": str(error.get("msg", "Invalid request.")),
            "type": str(error.get("type", "value_error")),
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": details})


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


class TaskCancellationRequestInput(BaseModel):
    attempt_id: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=500)


class GenerateImageRequest(BaseModel):
    prompt: str
    output_path: Optional[str] = None


class GenerateVideoRequest(BaseModel):
    prompt: str
    narration: Optional[str] = None
    output_path: Optional[str] = None


@app.get("/professor/voice", include_in_schema=False)
def professor_voice_ui():
    """Serve the browser-based voice interface; speech runs on the user's device."""
    return FileResponse(
        Path(__file__).resolve().parent / "static" / "professor_voice.html",
        media_type="text/html",
    )


@app.get("/professor/chat", include_in_schema=False)
def professor_chat_ui():
    """Serve the authenticated browser-first Professor conversation workspace."""
    return FileResponse(
        Path(__file__).resolve().parent / "static" / "professor_chat.html",
        media_type="text/html",
    )


@app.get("/professor/sources", include_in_schema=False)
def professor_sources_ui():
    """Serve the static Source Division operator interface; data remains API-key protected."""
    return FileResponse(Path(__file__).resolve().parent / "static" / "professor_sources.html", media_type="text/html")


@app.get("/health")
def health():
    return api.health()


@app.get("/launch/readiness")
def launch_readiness():
    """Return a non-secret launch checklist; configuration is not a live health check."""
    identity_configured = getattr(app.state, "identity_service", None) is not None
    tenant_storage_configured = bool(getattr(app.state, "tenant_data_path", None))
    conversation_service = getattr(app.state, "conversation_service", None)
    provider_configured = bool(
        conversation_service is not None
        and getattr(conversation_service, "is_configured", False)
    )
    hosted_login_settings = ("ATLAS_OIDC_CLIENT_ID", "ATLAS_OIDC_REDIRECT_URI")
    hosted_login_configured = all(os.getenv(name) for name in hosted_login_settings)

    checks = {
        "verified_api_identity": identity_configured,
        "hosted_browser_login_configuration": hosted_login_configured,
        "tenant_data_storage": tenant_storage_configured,
        "reasoning_provider_configured": provider_configured,
        # A configured URL/key does not prove that a live round trip works.
        "live_provider_round_trip_verified": False,
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return {
        "status": "ready_for_release_review" if not blockers else "not_ready",
        "checks": checks,
        "blockers": blockers,
        "execution_enabled": False,
        "note": (
            "Configuration presence is not a live service test. A human must "
            "verify a real provider conversation, hosted sign-in and deployment "
            "security before release."
        ),
    }


@app.get("/identity/me")
def identity_me(principal=Depends(require_verified_principal)):
    """Return the authenticated tenant principal for integration diagnostics."""
    return {
        "issuer": principal.issuer,
        "subject": principal.subject,
        "tenant_id": principal.tenant_id,
        "scopes": sorted(principal.scopes),
    }


@app.get("/identity/login-readiness")
def identity_login_readiness():
    """Expose non-secret deployment readiness for hosted OIDC login.

    This diagnostic never returns provider endpoints, client credentials,
    tokens, tenant membership, or permission data.
    """
    verifier_settings = (
        "ATLAS_OIDC_ISSUER",
        "ATLAS_OIDC_AUDIENCE",
        "ATLAS_OIDC_JWKS_URI",
        "ATLAS_OIDC_ALLOWED_ALGORITHMS",
        "ATLAS_MEMBERSHIP_DB_PATH",
    )
    hosted_login_settings = (
        "ATLAS_OIDC_CLIENT_ID",
        "ATLAS_OIDC_REDIRECT_URI",
    )
    missing_verifier = [name for name in verifier_settings if not os.getenv(name)]
    missing_login = [name for name in hosted_login_settings if not os.getenv(name)]
    required_login_routes = (
        ("GET", "/identity/login"),
        ("GET", "/identity/callback"),
    )
    registered_routes = {
        (method, getattr(route, "path", None))
        for route in app.routes
        for method in (getattr(route, "methods", None) or ())
    }
    missing_routes = [
        f"{method} {path}"
        for method, path in required_login_routes
        if (method, path) not in registered_routes
    ]

    if missing_verifier or missing_login:
        readiness_status = "not_configured"
    elif missing_routes:
        readiness_status = "not_implemented"
    else:
        # Route registration is not proof of a successful provider round trip.
        readiness_status = "routes_registered_unverified"

    return {
        "status": readiness_status,
        "api_verifier": {
            "configured": not missing_verifier,
            "missing_settings": missing_verifier,
        },
        "hosted_login": {
            "configured": not missing_login,
            "implemented": not missing_routes,
            "missing_settings": missing_login,
            "missing_routes": missing_routes,
            "flow": "authorization_code_pkce",
        },
        "note": (
            "This endpoint reports configuration and route registration only; "
            "it does not prove a successful sign-in or callback round trip."
        ),
    }



@app.post("/professor/tenant/plans", status_code=201)
def create_tenant_professor_plan(
    payload: TenantPlanCreateInput,
    principal=Depends(require_verified_principal),
):
    """Persist a tenant-owned DRAFT plan; creation never approves or executes it."""
    database_path = getattr(app.state, "tenant_data_path", None)
    if not database_path:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tenant plan storage is not configured.",
        )
    connection = sqlite3.connect(database_path, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        plan = ProfessorPlan(
            plan_id=uuid.uuid4().hex,
            objective=payload.objective,
            acceptance_criteria=tuple(payload.acceptance_criteria),
            steps=tuple(
                PlanStep(
                    step_id=item.step_id,
                    capability=item.capability,
                    objective=item.objective,
                    risk=item.risk,
                    depends_on=tuple(item.depends_on),
                    required_scopes=tuple(item.required_scopes),
                    expected_output=item.expected_output,
                    timeout_seconds=item.timeout_seconds,
                    resource_budget=item.resource_budget,
                    capability_version=item.capability_version,
                )
                for item in payload.steps
            ),
        )
        repository = TenantPlanRepository(connection, principal)
        repository.create(plan)
        return {
            "plan_id": plan.plan_id,
            "tenant_id": principal.tenant_id,
            "state": plan.state.value,
            "objective": plan.objective,
            "acceptance_criteria": list(plan.acceptance_criteria),
            "step_count": len(plan.steps),
            "execution_enabled": False,
        }
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Tenant plan creation denied.") from None
    except PlanValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Tenant plan could not be created.") from None
    except sqlite3.Error:
        raise HTTPException(
            status_code=503,
            detail="Tenant plan storage is temporarily unavailable.",
        ) from None
    finally:
        connection.close()


@app.get("/professor/tenant/plans/{plan_id}")
def inspect_tenant_professor_plan(
    plan_id: str,
    event_limit_per_step: int = 20,
    principal=Depends(require_verified_principal),
):
    """Inspect one tenant-owned Professor plan without dispatching any work."""
    database_path = getattr(app.state, "tenant_data_path", None)
    if not database_path:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tenant plan storage is not configured.",
        )
    if not 1 <= event_limit_per_step <= 100:
        raise HTTPException(status_code=422, detail="event_limit_per_step must be between 1 and 100.")
    connection = sqlite3.connect(database_path, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        plans = TenantPlanRepository(connection, principal)
        steps = TenantStepExecutionRepository(connection, principal)
        service = TenantProfessorOrchestrationService(
            principal, plans, steps, getattr(app.state, "tenant_capability_registry", CapabilityRegistry())
        )
        report = service.inspect_plan(
            plan_id, event_limit_per_step=event_limit_per_step
        )
        readiness = None
        if report.readiness is not None:
            readiness = {
                "plan_state": report.readiness.plan_state.value,
                "ordered_step_ids": list(report.readiness.ordered_step_ids),
                "structurally_ready_step_ids": list(report.readiness.structurally_ready_step_ids),
                "blocked_step_ids": list(report.readiness.blocked_step_ids),
                "execution_enabled": report.readiness.execution_enabled,
                "steps": [
                    {
                        "step_id": item.step_id,
                        "capability": item.capability,
                        "capability_version": item.capability_version,
                        "readiness": item.readiness.value,
                        "reasons": list(item.reasons),
                    }
                    for item in report.readiness.steps
                ],
            }
        return {
            "tenant_id": report.tenant_id,
            "plan": {
                "plan_id": report.plan.plan_id,
                "objective": report.plan.objective,
                "state": report.plan.state.value,
                "acceptance_criteria": list(report.plan.acceptance_criteria),
                "steps": [
                    {
                        "step_id": item.step_id,
                        "capability": item.capability,
                        "objective": item.objective,
                        "risk": item.risk.value,
                        "depends_on": list(item.depends_on),
                        "required_scopes": list(item.required_scopes),
                        "capability_version": item.capability_version,
                    }
                    for item in report.plan.steps
                ],
            },
            "transitions": [
                {
                    "from_state": item.from_state.value if item.from_state else None,
                    "to_state": item.to_state.value,
                    "actor_issuer": item.actor_issuer,
                    "actor_subject": item.actor_subject,
                    "created_at": item.created_at,
                }
                for item in report.transitions
            ],
            "step_runs": [
                {
                    "step_id": item.step_id,
                    "state": item.state,
                    "attempt_number": item.attempt_number,
                    "worker_id": item.worker_id,
                    "fencing_token": item.fencing_token,
                    "lease_expires_at": item.lease_expires_at,
                    "result": item.result,
                    "error_code": item.error_code,
                }
                for item in report.steps
            ],
            "recent_events": [
                {
                    "step_id": item.step_id,
                    "event_type": item.event_type,
                    "attempt_number": item.attempt_number,
                    "worker_id": item.worker_id,
                    "fencing_token": item.fencing_token,
                    "details": item.details,
                    "created_at": item.created_at,
                }
                for item in report.recent_events
            ],
            "readiness": readiness,
            "execution_enabled": report.execution_enabled,
            "execution_block_reason": report.execution_block_reason,
        }
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Tenant plan access denied.") from None
    except (TenantPlanNotFound, TenantStepNotFound):
        raise HTTPException(status_code=404, detail="Plan was not found.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(
            status_code=503,
            detail="Tenant plan storage is temporarily unavailable.",
        ) from None
    finally:
        connection.close()


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


@app.post("/tasks/{task_id}/cancel", dependencies=[Depends(require_api_key)])
def request_task_cancellation_route(task_id: str, payload: TaskCancellationRequestInput):
    if manager.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        cancellation = storage.request_task_cancellation(
            task_id, payload.attempt_id, payload.actor, payload.reason
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if cancellation is None:
        raise HTTPException(status_code=409, detail="The attempt is not currently owned by a live worker.")
    return {
        "status": cancellation["state"],
        "cancellation": cancellation,
    }


@app.get("/tasks/{task_id}/cancellation", dependencies=[Depends(require_api_key)])
def get_task_cancellation_route(task_id: str):
    if manager.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return storage.get_task_cancellation(task_id)


_RETRY_SCHEDULE_RESPONSE_FIELDS = (
    "schedule_id", "task_id", "originating_attempt_id", "next_attempt_number",
    "due_at", "deadline_at", "capability_name", "capability_version",
    "error_code", "state", "created_at", "claimed_at", "claimed_attempt_id",
    "task_title", "task_status", "task_attempts",
)


def _public_retry_schedule(record: dict[str, Any]) -> dict[str, Any]:
    """Expose schedule status without leaking idempotency keys or internal snapshots."""
    return {
        field: record[field]
        for field in _RETRY_SCHEDULE_RESPONSE_FIELDS
        if field in record
    }


@app.get("/tasks/{task_id}/retry-schedules", dependencies=[Depends(require_api_key)])
def list_task_retry_schedules_route(task_id: str):
    if manager.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return [
        _public_retry_schedule(record)
        for record in storage.list_task_retry_schedules(task_id)
    ]


@app.get("/tasks/retries/due", dependencies=[Depends(require_api_key)])
def list_due_retry_schedules_route(limit: int = 50):
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 100")
    return [
        _public_retry_schedule(record)
        for record in storage.list_due_task_retry_schedules(limit=limit)
    ]


@app.post("/tasks/retries/expire", dependencies=[Depends(require_api_key)])
def expire_retry_schedules_route(limit: int = 100):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 500")
    return {
        "expired": storage.expire_task_retry_schedules(limit=limit),
        "status": "retry_deadlines_scanned",
    }


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
    """Keep review disabled until a trusted identity provider supplies a verified principal."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Proposal review is temporarily disabled until verified human identity and tenant authorization are configured.",
    )



@app.get("/learning/overview", dependencies=[Depends(require_api_key)])
def learning_overview_route(limit: int = 10):
    """Expose bounded learning observability without lesson evidence or task payloads."""
    if limit < 1 or limit > 50:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 50")
    return storage.get_learning_overview(recent_limit=limit)


@app.get("/professor/learning", include_in_schema=False)
def professor_learning_ui():
    """Serve the read-only learning observability operator interface."""
    return FileResponse(
        Path(__file__).resolve().parent / "static" / "professor_learning.html",
        media_type="text/html",
    )


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


def run_server() -> None:
    """Start the development server without exposing an unauthenticated local instance."""
    import uvicorn

    host = "0.0.0.0" if API_REQUIRE_AUTH else "127.0.0.1"
    uvicorn.run("app:app", host=host, port=8000, reload=False)


if __name__ == "__main__":
    run_server()
