"""Verified, tenant-scoped API for explicit Professor memory management."""
from __future__ import annotations

import sqlite3
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .http_identity import require_verified_principal
from .identity_policy import AuthorizationDenied
from .tenant_professor_memory import MemoryNotFound, TenantProfessorMemoryRepository

router = APIRouter()


class MemoryProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=2000)
    retention_days: int = Field(default=90, ge=1, le=3650)


class MemoryDecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str = Field(pattern="^(approved|rejected)$")
    rationale: str = Field(default="", max_length=500)




class MemorySupersessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    replacement_proposal_id: str = Field(min_length=1, max_length=128)
    confirmed: StrictBool
    rationale: str = Field(default="", max_length=500)


class MemoryQueryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=20)


def _repository(request: Request, principal):
    path = getattr(request.app.state, "tenant_data_path", None)
    if not path:
        raise HTTPException(status_code=503, detail="Professor memory storage is not configured.")
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    return db, TenantProfessorMemoryRepository(db, principal)


@router.post("/professor/memory/proposals", status_code=201)
def propose_memory(payload: MemoryProposalInput, request: Request,
                   principal=Depends(require_verified_principal)):
    db, repository = _repository(request, principal)
    try:
        proposal = repository.propose(
            uuid.uuid4().hex, category=payload.category, title=payload.title,
            content=payload.content, retention_days=payload.retention_days,
        )
        return {
            "proposal_id": proposal.proposal_id, "category": proposal.category,
            "title": proposal.title, "content": proposal.content,
            "status": proposal.status, "expires_at": proposal.expires_at,
            "created_at": proposal.created_at,
        }
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Memory proposal access denied.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Professor memory storage is temporarily unavailable.") from None
    finally:
        db.close()


@router.get("/professor/memory/proposals")
def list_memory_proposals(request: Request, status: str = "pending", limit: int = 50,
                          principal=Depends(require_verified_principal)):
    db, repository = _repository(request, principal)
    try:
        return {"proposals": list(repository.list_proposals(status=status, limit=limit))}
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Memory access denied.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Professor memory storage is temporarily unavailable.") from None
    finally:
        db.close()


@router.post("/professor/memory/proposals/{proposal_id}/decision")
def decide_memory(proposal_id: str, payload: MemoryDecisionInput, request: Request,
                  principal=Depends(require_verified_principal)):
    db, repository = _repository(request, principal)
    try:
        repository.decide(proposal_id, decision=payload.decision, rationale=payload.rationale)
        return {"proposal_id": proposal_id, "status": payload.decision,
                "retrieval_enabled": payload.decision == "approved"}
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Memory approval access denied.") from None
    except MemoryNotFound:
        raise HTTPException(status_code=404, detail="Memory proposal was not found.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Professor memory storage is temporarily unavailable.") from None
    finally:
        db.close()


@router.post("/professor/memory/retrieve")
def retrieve_memory(payload: MemoryQueryInput, request: Request,
                    principal=Depends(require_verified_principal)):
    db, repository = _repository(request, principal)
    try:
        return {"memories": list(repository.retrieve(payload.query, limit=payload.limit)),
                "mode": "bounded_lexical", "execution_enabled": False}
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Memory retrieval access denied.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Professor memory storage is temporarily unavailable.") from None
    finally:
        db.close()


@router.delete("/professor/memory/{proposal_id}", status_code=204)
def delete_memory(proposal_id: str, request: Request,
                  principal=Depends(require_verified_principal)):
    db, repository = _repository(request, principal)
    try:
        repository.delete(proposal_id)
        return None
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Memory deletion access denied.") from None
    except MemoryNotFound:
        raise HTTPException(status_code=404, detail="Memory item was not found.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Professor memory storage is temporarily unavailable.") from None
    finally:
        db.close()

@router.post("/professor/memory/cleanup")
def cleanup_expired_memory(request: Request, limit: int = 100,
                           principal=Depends(require_verified_principal)):
    """Permanently purge a bounded number of expired records owned by this user."""
    db, repository = _repository(request, principal)
    try:
        deleted = repository.purge_expired(limit=limit)
        return {"deleted": deleted, "status": "expired_memory_cleanup_complete"}
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Memory cleanup access denied.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Professor memory storage is temporarily unavailable.") from None
    finally:
        db.close()


@router.post("/professor/memory/proposals/{prior_proposal_id}/supersession")
def confirm_memory_supersession(prior_proposal_id: str, payload: MemorySupersessionInput,
                                 request: Request,
                                 principal=Depends(require_verified_principal)):
    """Replace an approved memory only after an explicit owner confirmation."""
    db, repository = _repository(request, principal)
    try:
        repository.confirm_supersession(
            prior_proposal_id, payload.replacement_proposal_id,
            confirmed=payload.confirmed, rationale=payload.rationale,
        )
        return {
            "prior_proposal_id": prior_proposal_id,
            "replacement_proposal_id": payload.replacement_proposal_id,
            "status": "superseded",
            "retrieval_updated": True,
        }
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Memory supersession access denied.") from None
    except MemoryNotFound:
        raise HTTPException(status_code=404, detail="Both memory proposals must belong to this owner.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Professor memory storage is temporarily unavailable.") from None
    finally:
        db.close()


@router.get("/professor/memory/supersessions")
def list_memory_supersessions(request: Request, limit: int = 50,
                              principal=Depends(require_verified_principal)):
    db, repository = _repository(request, principal)
    try:
        return {"supersessions": list(repository.list_supersessions(limit=limit))}
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Memory access denied.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Professor memory storage is temporarily unavailable.") from None
    finally:
        db.close()
