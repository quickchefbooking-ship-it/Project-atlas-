"""Authenticated, tenant-scoped HTTP API for Professor text conversations.

The route accepts only a user message. Identity, tenant and scopes come from
the verified server principal; assistant messages are written only after the
injected reasoning service returns successfully. No tools or external actions.
"""
from __future__ import annotations

import sqlite3
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from .conversation_contract import ConversationMessage, build_conversation_input
from .conversation_service import ConversationNotConfigured
from .http_identity import require_verified_principal
from .identity_policy import AuthorizationDenied, RequestPrincipal
from .openai_compatible_provider import ReasoningProviderError
from .tenant_conversation_repository import (
    ConversationNotFound,
    TenantConversationRepository,
)

router = APIRouter()


class ProfessorTurnInput(BaseModel):
    model_config = {"extra": "forbid"}
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: Optional[str] = Field(default=None, min_length=1, max_length=128)


def _repository(request: Request, principal: RequestPrincipal):
    path = getattr(request.app.state, "tenant_data_path", None)
    if not path:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Professor conversation storage is not configured.",
        )
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    return db, TenantConversationRepository(db, principal)


@router.post("/professor/conversation")
def professor_conversation(
    payload: ProfessorTurnInput,
    request: Request,
    principal: RequestPrincipal = Depends(require_verified_principal),
):
    """Create or continue one private conversation and return one text answer."""
    service = getattr(request.app.state, "conversation_service", None)
    if service is None or not service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Professor's reasoning provider is not configured.",
        )
    db, repository = _repository(request, principal)
    conversation_id = payload.conversation_id or uuid.uuid4().hex
    try:
        is_new_conversation = payload.conversation_id is None
        if is_new_conversation:
            prior_messages = ()
        else:
            prior = repository.get(conversation_id, limit=23)
            prior_messages = tuple(
                ConversationMessage(item.role, item.content)
                for item in prior.messages
            )
        conversation = build_conversation_input(
            conversation_id=conversation_id,
            user_id=principal.subject,
            prior_messages=prior_messages,
            latest_user_message=payload.message,
        )
        result = service.respond(conversation)
        if is_new_conversation:
            repository.create(conversation_id)
        repository.append(conversation_id, "user", payload.message)
        repository.append(conversation_id, "assistant", result.text)
        return {
            "conversation_id": conversation_id,
            "response": result.text,
            "provider": result.provider,
            "model": result.model,
        }
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Conversation access denied.") from None
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation not found.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except (ConversationNotConfigured, ReasoningProviderError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Professor could not complete this response. Your message may be saved; retry safely.",
        ) from None
    except sqlite3.Error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Professor conversation storage is temporarily unavailable.",
        ) from None
    finally:
        db.close()


@router.get("/professor/conversations")
def list_professor_conversations(
    request: Request,
    principal: RequestPrincipal = Depends(require_verified_principal),
):
    db, repository = _repository(request, principal)
    try:
        return {"conversations": list(repository.list(limit=100))}
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Conversation access denied.") from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Conversation storage is temporarily unavailable.") from None
    finally:
        db.close()


@router.get("/professor/conversations/{conversation_id}")
def get_professor_conversation(
    conversation_id: str,
    request: Request,
    principal: RequestPrincipal = Depends(require_verified_principal),
):
    db, repository = _repository(request, principal)
    try:
        item = repository.get(conversation_id, limit=100)
        return {
            "conversation_id": item.conversation_id,
            "messages": [
                {"ordinal": message.ordinal, "role": message.role,
                 "content": message.content, "created_at": message.created_at}
                for message in item.messages
            ],
        }
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Conversation access denied.") from None
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation not found.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Conversation storage is temporarily unavailable.") from None
    finally:
        db.close()


@router.delete("/professor/conversations/{conversation_id}", status_code=204)
def delete_professor_conversation(
    conversation_id: str,
    request: Request,
    principal: RequestPrincipal = Depends(require_verified_principal),
):
    db, repository = _repository(request, principal)
    try:
        repository.delete(conversation_id)
        return None
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Conversation deletion denied.") from None
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation not found.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Conversation storage is temporarily unavailable.") from None
    finally:
        db.close()
