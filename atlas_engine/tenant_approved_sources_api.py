"""Authenticated tenant-owned evidence source ingestion and approval routes.

Tenant and reviewer identities are derived only from the verified principal.
Client payloads cannot choose either identity or cross tenant boundaries.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .http_identity import require_verified_principal
from .identity_policy import AuthorizationDenied, authorize_tenant_resource
from .tenant_approved_sources import (
    review_tenant_source_document,
    stage_tenant_source_document,
)

router = APIRouter()


class TenantSourceStageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=500)
    uri: str = Field(min_length=1, max_length=2048)
    content: str = Field(min_length=1, max_length=1_000_000)
    content_type: str = Field(default="text/html", pattern="^(text/html|text/plain|application/pdf)$")
    metadata: dict = Field(default_factory=dict)


class TenantSourceReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str = Field(pattern="^(approved|rejected)$")
    trust_level: str = Field(default="reviewed", pattern="^(reviewed|authoritative)$")


def _verified_reviewer_id(principal) -> str:
    digest = hashlib.sha256(
        (principal.issuer + "\0" + principal.subject).encode("utf-8")
    ).hexdigest()
    return "reviewer:" + digest[:32]


def _tenant_database(request: Request):
    path = getattr(request.app.state, "tenant_data_path", None)
    if not path:
        raise HTTPException(status_code=503, detail="Tenant source storage is not configured.")
    try:
        connection = sqlite3.connect(path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Tenant source storage is temporarily unavailable.") from None


@router.post("/professor/tenant/sources")
def stage_tenant_source(
    payload: TenantSourceStageInput,
    request: Request,
    principal=Depends(require_verified_principal),
):
    """Stage a source as pending; staging never approves or trusts the content."""
    try:
        authorize_tenant_resource(principal, principal.tenant_id, {"evidence:source:write"})
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Tenant source submission denied.") from None

    connection = _tenant_database(request)
    try:
        staged = stage_tenant_source_document(
            connection,
            tenant_id=principal.tenant_id,
            staged_by=_verified_reviewer_id(principal),
            title=payload.title,
            uri=payload.uri,
            content=payload.content,
            content_type=payload.content_type,
            metadata=payload.metadata,
        )
        connection.commit()
        return {"status": "staged_for_review", **staged}
    except ValueError as exc:
        connection.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except (sqlite3.Error, TypeError):
        connection.rollback()
        raise HTTPException(status_code=503, detail="Tenant source storage is temporarily unavailable.") from None
    finally:
        connection.close()


@router.post("/professor/tenant/sources/{document_id}/review")
def review_tenant_source(
    document_id: str,
    payload: TenantSourceReviewInput,
    request: Request,
    principal=Depends(require_verified_principal),
):
    """Approve/reject a pending source with identity and tenant from verified auth."""
    try:
        authorize_tenant_resource(principal, principal.tenant_id, {"evidence:source:approve"})
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Tenant source approval denied.") from None

    connection = _tenant_database(request)
    try:
        reviewed = review_tenant_source_document(
            connection,
            tenant_id=principal.tenant_id,
            document_id=document_id,
            reviewer_id=_verified_reviewer_id(principal),
            decision=payload.decision,
            trust_level=payload.trust_level,
        )
        connection.commit()
        return {"status": "source_reviewed", **reviewed}
    except ValueError as exc:
        connection.rollback()
        # Do not disclose whether a document ID exists in another tenant.
        raise HTTPException(status_code=404, detail="Pending source document was not found for this tenant.") from None
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(status_code=503, detail="Tenant source storage is temporarily unavailable.") from None
    finally:
        connection.close()
