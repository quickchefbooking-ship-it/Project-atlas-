"""Authenticated read-only endpoint for Professor reasoning audit traces."""
from __future__ import annotations
import sqlite3
from fastapi import APIRouter, Depends, HTTPException, Request
from .http_identity import require_verified_principal
from .tenant_conversation_repository import ConversationNotFound, TenantConversationRepository
from .tenant_reasoning_audit import TenantReasoningAuditRepository

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
