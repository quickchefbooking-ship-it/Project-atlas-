"""Authenticated read-only endpoint for Professor reasoning audit traces."""
from __future__ import annotations
import sqlite3
from fastapi import APIRouter, Depends, HTTPException, Request
from .http_identity import require_verified_principal
from .tenant_conversation_repository import ConversationNotFound, TenantConversationRepository
from .tenant_reasoning_audit import TenantReasoningAuditRepository
from .tenant_evaluation_repository import TenantEvaluationRepository

router = APIRouter()


@router.get("/professor/conversations/{conversation_id}/audit")
def list_professor_reasoning_audit(conversation_id: str, request: Request,
                                   limit: int = 50,
                                   principal=Depends(require_verified_principal)):
    path = getattr(request.app.state, "tenant_data_path", None)
    if not path:
        raise HTTPException(status_code=503, detail="Reasoning audit storage is not configured.")
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        TenantConversationRepository(db, principal).get(conversation_id, limit=1)
        records = TenantReasoningAuditRepository(db, principal).list(conversation_id, limit=limit)
        return {"audit": [{
            "audit_id": item.audit_id, "conversation_id": item.conversation_id,
            "request_sha256": item.request_sha256, "response_sha256": item.response_sha256,
            "context_sha256": item.context_sha256, "provider": item.provider,
            "model": item.model, "evidence": list(item.evidence),
            "previous_hash": item.previous_hash, "record_hash": item.record_hash,
            "created_at": item.created_at,
            "raw_content_stored": False,
        } for item in records]}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Reasoning audit access denied.") from None
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation was not found.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Reasoning audit storage is temporarily unavailable.") from None
    finally:
        db.close()


@router.get("/professor/conversations/{conversation_id}/audit/verify")
def verify_professor_reasoning_audit(conversation_id: str, request: Request,
                                     principal=Depends(require_verified_principal)):
    path = getattr(request.app.state, "tenant_data_path", None)
    if not path:
        raise HTTPException(status_code=503, detail="Reasoning audit storage is not configured.")
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        TenantConversationRepository(db, principal).get(conversation_id, limit=1)
        result = TenantReasoningAuditRepository(db, principal).verify_chain()
        return {"verification": result}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Reasoning audit access denied.") from None
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation was not found.") from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Reasoning audit storage is temporarily unavailable.") from None
    finally:
        db.close()


@router.get("/professor/conversations/{conversation_id}/trace")
def get_professor_reasoning_trace(conversation_id: str, request: Request,
                                  principal=Depends(require_verified_principal)):
    """Return one bounded, read-only view of an owned conversation's trace."""
    path = getattr(request.app.state, "tenant_data_path", None)
    if not path:
        raise HTTPException(status_code=503, detail="Professor trace storage is not configured.")
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        conversation = TenantConversationRepository(db, principal).get(conversation_id, limit=100)
        audit_repo = TenantReasoningAuditRepository(db, principal)
        audit = audit_repo.list(conversation_id, limit=100)
        verification = audit_repo.verify_chain()
        evaluations = []
        evaluations_available = True
        try:
            evaluations = TenantEvaluationRepository(db, principal).list(
                limit=100, subject_type="conversation", subject_id=conversation_id
            )
        except PermissionError:
            evaluations_available = False
        return {
            "conversation_id": conversation.conversation_id,
            "conversation": {
                "messages": [
                    {"ordinal": message.ordinal, "role": message.role,
                     "content": message.content, "created_at": message.created_at}
                    for message in conversation.messages
                ],
                "truncated": len(conversation.messages) >= 100,
            },
            "reasoning_audit": [{
                "audit_id": item.audit_id,
                "request_sha256": item.request_sha256,
                "response_sha256": item.response_sha256,
                "context_sha256": item.context_sha256,
                "provider": item.provider, "model": item.model,
                "evidence": list(item.evidence),
                "previous_hash": item.previous_hash,
                "record_hash": item.record_hash,
                "created_at": item.created_at,
                "raw_content_stored": False,
            } for item in audit],
            "audit_verification": verification,
            "evaluations": [{
                "evaluation_id": item.evaluation_id, "outcome": item.outcome,
                "rating": item.rating, "note": item.note,
                "evidence": list(item.evidence), "created_at": item.created_at,
            } for item in evaluations],
            "evaluations_available": evaluations_available,
            "execution_enabled": False,
            "learning_policy": "Feedback is review evidence only; no automatic prompt, policy, permission or model changes.",
        }
    except PermissionError:
        raise HTTPException(status_code=403, detail="Professor trace access denied.") from None
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation was not found.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Professor trace storage is temporarily unavailable.") from None
    finally:
        db.close()
