"""Authenticated append-only source publication/retraction assessment route."""
from __future__ import annotations

import hashlib
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .http_identity import require_verified_principal
from .identity_policy import AuthorizationDenied, authorize_tenant_resource
from .tenant_source_assessments import append_tenant_source_assessment, list_tenant_source_assessments

router = APIRouter()


class TenantSourceAssessmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    publication_status: str = Field(default="unknown", pattern="^(published|preprint|unpublished|unknown)$")
    retraction_status: str = Field(default="unknown", pattern="^(not_known|correction_notice|expression_of_concern|retracted|unknown)$")
    study_design: str = Field(default="unknown", pattern="^(randomized_trial|observational|systematic_review|meta_analysis|case_report|qualitative|guideline|other|unknown)$")
    evidence_references: list[str] = Field(default_factory=list, max_length=10)
    rationale: str = Field(min_length=1, max_length=4000)
    supersedes_assessment_id: str | None = Field(default=None, min_length=1, max_length=128)
    revision_reason: str | None = Field(default=None, min_length=1, max_length=1000)


def _reviewer_id(principal) -> str:
    digest = hashlib.sha256(
        (principal.issuer + "\0" + principal.subject).encode("utf-8")
    ).hexdigest()
    return "reviewer:" + digest[:32]


@router.post("/professor/tenant/sources/{document_id}/assessments")
def append_source_assessment(
    document_id: str,
    payload: TenantSourceAssessmentInput,
    request: Request,
    principal=Depends(require_verified_principal),
):
    """Record a human-attributed, evidence-referenced status assessment."""
    try:
        authorize_tenant_resource(
            principal, principal.tenant_id, {"evidence:source:assess"}
        )
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Tenant source assessment denied.") from None

    path = getattr(request.app.state, "tenant_data_path", None)
    if not path:
        raise HTTPException(status_code=503, detail="Tenant source storage is not configured.")
    try:
        connection = sqlite3.connect(path, timeout=5)
        connection.row_factory = sqlite3.Row
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Tenant source storage is temporarily unavailable.") from None
    try:
        result = append_tenant_source_assessment(
            connection,
            tenant_id=principal.tenant_id,
            document_id=document_id,
            reviewer_id=_reviewer_id(principal),
            publication_status=payload.publication_status,
            retraction_status=payload.retraction_status,
            study_design=payload.study_design,
            evidence_references=payload.evidence_references,
            rationale=payload.rationale,
            supersedes_assessment_id=payload.supersedes_assessment_id,
            revision_reason=payload.revision_reason,
        )
        connection.commit()
        return {"status": "assessment_recorded", **result}
    except ValueError as exc:
        connection.rollback()
        message = str(exc)
        if "Approved source document" in message:
            raise HTTPException(status_code=404, detail="Approved source document was not found for this tenant.") from None
        raise HTTPException(status_code=422, detail=message) from None
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(status_code=503, detail="Tenant source storage is temporarily unavailable.") from None
    finally:
        connection.close()



@router.get("/professor/tenant/sources/{document_id}/assessments")
def get_source_assessment_history(
    document_id: str,
    request: Request,
    principal=Depends(require_verified_principal),
):
    """Read assessment history inside the verified tenant boundary."""
    try:
        authorize_tenant_resource(
            principal, principal.tenant_id, {"evidence:source:read"}
        )
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Tenant source assessment access denied.") from None

    path = getattr(request.app.state, "tenant_data_path", None)
    if not path:
        raise HTTPException(status_code=503, detail="Tenant source storage is not configured.")
    try:
        connection = sqlite3.connect(path, timeout=5)
        connection.row_factory = sqlite3.Row
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Tenant source storage is temporarily unavailable.") from None
    try:
        history = list_tenant_source_assessments(
            connection, tenant_id=principal.tenant_id, document_id=document_id,
        )
        return {"status": "assessment_history", "assessments": history}
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Tenant source storage is temporarily unavailable.") from None
    finally:
        connection.close()
