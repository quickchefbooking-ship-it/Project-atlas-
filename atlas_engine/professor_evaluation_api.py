"""Authenticated tenant endpoints for explicit Professor feedback."""
from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .http_identity import require_verified_principal
from .tenant_conversation_repository import ConversationNotFound, TenantConversationRepository
from .tenant_evaluation_repository import TenantEvaluationRepository

router = APIRouter()


class EvaluationInput(BaseModel):
    model_config = {"extra": "forbid"}
    subject_type: Literal["conversation", "plan", "task"]
    subject_id: str = Field(min_length=1, max_length=128)
    outcome: Literal["helpful", "partially_helpful", "not_helpful", "successful", "unsuccessful", "unknown"]
    rating: int | None = Field(default=None, ge=1, le=5)
    note: str = Field(default="", max_length=2000)
    evidence: list[dict[str, str]] = Field(default_factory=list, max_length=10)


def _open(request: Request, principal):
    path = getattr(request.app.state, "tenant_data_path", None)
    if not path:
        raise HTTPException(status_code=503, detail="Tenant evaluation storage is not configured.")
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    return db, TenantEvaluationRepository(db, principal)


@router.post("/professor/tenant/evaluations", status_code=201)
def create_professor_evaluation(payload: EvaluationInput, request: Request,
                                principal=Depends(require_verified_principal)):
    db, repository = _open(request, principal)
    try:
        if payload.subject_type == "conversation":
            conversations = TenantConversationRepository(db, principal)
            conversations.get(payload.subject_id, limit=1)
        elif payload.subject_type == "plan":
            from .tenant_plan_repository import TenantPlanRepository
            TenantPlanRepository(db, principal).get(payload.subject_id)
        record = repository.record(
            subject_type=payload.subject_type, subject_id=payload.subject_id,
            outcome=payload.outcome, rating=payload.rating, note=payload.note,
            evidence=payload.evidence,
        )
        return {
            "evaluation_id": record.evaluation_id,
            "subject_type": record.subject_type,
            "subject_id": record.subject_id,
            "outcome": record.outcome,
            "rating": record.rating,
            "created_at": record.created_at,
            "learning_policy": "Stored for human review only; no automatic policy, prompt, permission or model changes.",
        }
    except PermissionError:
        raise HTTPException(status_code=403, detail="Evaluation access denied.") from None
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation was not found.") from None
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Evaluation storage is temporarily unavailable.") from None
    finally:
        db.close()


@router.get("/professor/tenant/evaluations")
def list_professor_evaluations(request: Request, limit: int = 50,
                               subject_type: str | None = None,
                               subject_id: str | None = None,
                               principal=Depends(require_verified_principal)):
    db, repository = _open(request, principal)
    try:
        records = repository.list(limit=limit, subject_type=subject_type, subject_id=subject_id)
        return {"evaluations": [
            {"evaluation_id": item.evaluation_id, "subject_type": item.subject_type,
             "subject_id": item.subject_id, "outcome": item.outcome,
             "rating": item.rating, "note": item.note, "evidence": list(item.evidence),
             "created_at": item.created_at}
            for item in records
        ]}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Evaluation access denied.") from None
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Evaluation storage is temporarily unavailable.") from None
    finally:
        db.close()
