"""Tenant-scoped, authenticated human review of completed evidence bundles.

Review records are append-only and never mutate immutable step execution results.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .http_identity import require_verified_principal
from .identity_policy import AuthorizationDenied, authorize_tenant_resource
from .reviewer_annotations import apply_reviewer_annotations
from .tenant_plan_repository import TenantPlanNotFound
from .tenant_step_execution_repository import (
    TenantStepExecutionRepository, TenantStepNotFound,
)

router = APIRouter()


class ReviewerAnnotationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=2000)
    source_id: str = Field(min_length=1, max_length=256)
    relation: str = Field(pattern="^(supports|challenges|mentions)$")


class EvidenceReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    annotations: list[ReviewerAnnotationInput] = Field(min_length=1, max_length=400)


def initialize_tenant_evidence_review_schema(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS tenant_evidence_reviews (
      review_id INTEGER PRIMARY KEY AUTOINCREMENT,
      tenant_id TEXT NOT NULL,
      plan_id TEXT NOT NULL,
      bundle_step_id TEXT NOT NULL,
      reviewer_id TEXT NOT NULL,
      reviewed_at TEXT NOT NULL,
      bundle_json TEXT NOT NULL,
      annotation_count INTEGER NOT NULL CHECK(annotation_count BETWEEN 1 AND 400),
      FOREIGN KEY(tenant_id,plan_id,bundle_step_id)
        REFERENCES tenant_professor_step_runs(tenant_id,plan_id,step_id)
        ON DELETE RESTRICT
    );
    CREATE INDEX IF NOT EXISTS idx_tenant_evidence_reviews_latest
      ON tenant_evidence_reviews(tenant_id,plan_id,bundle_step_id,review_id DESC);
    CREATE TRIGGER IF NOT EXISTS tenant_evidence_reviews_no_update
      BEFORE UPDATE ON tenant_evidence_reviews BEGIN
      SELECT RAISE(ABORT,'evidence review history is append-only');
    END;
    CREATE TRIGGER IF NOT EXISTS tenant_evidence_reviews_no_delete
      BEFORE DELETE ON tenant_evidence_reviews BEGIN
      SELECT RAISE(ABORT,'evidence review history is append-only');
    END;
    """)


def _reviewer_id(principal) -> str:
    # Stable pseudonymous attribution; raw OIDC subject and issuer are not stored.
    digest = hashlib.sha256(
        (principal.issuer + "\\0" + principal.subject).encode("utf-8")
    ).hexdigest()
    return "reviewer:" + digest[:32]


def _load_bundle(db, tenant_id: str, plan_id: str, step_id: str):
    row = db.execute("""
      SELECT r.state,r.result_json,p.capability
      FROM tenant_professor_step_runs r
      JOIN tenant_professor_plan_steps p
        ON p.tenant_id=r.tenant_id AND p.plan_id=r.plan_id AND p.step_id=r.step_id
      JOIN tenant_professor_plans plan
        ON plan.tenant_id=r.tenant_id AND plan.plan_id=r.plan_id
      WHERE r.tenant_id=? AND r.plan_id=? AND r.step_id=?
    """, (tenant_id, plan_id, step_id)).fetchone()
    if row is None:
        raise TenantStepNotFound("Evidence bundle was not found.")
    if row["state"] != "succeeded" or row["result_json"] is None:
        raise ValueError("Only a successfully completed evidence bundle can be reviewed.")
    if row["capability"] != "research.evidence.bundle":
        raise ValueError("The selected step is not an evidence bundle.")
    bundle = json.loads(row["result_json"])
    if not isinstance(bundle, dict) or bundle.get("schema_version") != 1:
        raise ValueError("The completed step is not a supported evidence bundle.")
    return bundle


@router.post("/professor/tenant/plans/{plan_id}/evidence/{bundle_step_id}/review")
def submit_evidence_review(
    plan_id: str,
    bundle_step_id: str,
    payload: EvidenceReviewInput,
    request: Request,
    principal=Depends(require_verified_principal),
):
    """Append a reviewer-attributed revision for this tenant's completed bundle."""
    try:
        authorize_tenant_resource(principal, principal.tenant_id, {"evidence:review"})
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Evidence review access denied.") from None
    database_path = getattr(request.app.state, "tenant_data_path", None)
    if not database_path:
        raise HTTPException(status_code=503, detail="Tenant review storage is not configured.")
    connection = sqlite3.connect(database_path, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        initialize_tenant_evidence_review_schema(connection)
        steps = TenantStepExecutionRepository(connection, principal)
        # get_step applies the separate steps:read boundary and tenant filter.
        step = steps.get_step(plan_id, bundle_step_id)
        if step.state != "succeeded" or step.capability != "research.evidence.bundle":
            raise ValueError("Only a completed evidence bundle can be reviewed.")
        original = _load_bundle(connection, principal.tenant_id, plan_id, bundle_step_id)
        # Serialize concurrent reviewers so each revision builds on the
        # latest committed bundle instead of overwriting another review's work.
        connection.execute("BEGIN IMMEDIATE")
        latest = connection.execute("""
          SELECT bundle_json FROM tenant_evidence_reviews
          WHERE tenant_id=? AND plan_id=? AND bundle_step_id=?
          ORDER BY review_id DESC LIMIT 1
        """, (principal.tenant_id, plan_id, bundle_step_id)).fetchone()
        base = json.loads(latest["bundle_json"]) if latest else original
        reviewer_id = _reviewer_id(principal)
        reviewed_at = datetime.now(timezone.utc).isoformat()
        reviewed = apply_reviewer_annotations(
            base, [item.model_dump() for item in payload.annotations],
            reviewer_id=reviewer_id, reviewed_at=reviewed_at,
        )
        encoded = json.dumps(reviewed, ensure_ascii=False, allow_nan=False,
                             sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 65536:
            raise ValueError("Reviewed evidence bundle exceeds the 64 KiB limit.")
        connection.execute("""
          INSERT INTO tenant_evidence_reviews
            (tenant_id,plan_id,bundle_step_id,reviewer_id,reviewed_at,bundle_json,annotation_count)
          VALUES(?,?,?,?,?,?,?)
        """, (principal.tenant_id, plan_id, bundle_step_id, reviewer_id,
              reviewed_at, encoded, len(payload.annotations)))
        connection.commit()
        revision = connection.execute("""
          SELECT MAX(review_id) AS revision FROM tenant_evidence_reviews
          WHERE tenant_id=? AND plan_id=? AND bundle_step_id=?
        """, (principal.tenant_id, plan_id, bundle_step_id)).fetchone()["revision"]
        return {
            "status": "review_recorded", "plan_id": plan_id,
            "bundle_step_id": bundle_step_id, "revision": revision,
            "annotation_count": len(payload.annotations),
            "reviewer_id": reviewer_id, "reviewed_at": reviewed_at,
            "bundle": reviewed,
        }
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Evidence review access denied.") from None
    except (TenantStepNotFound, TenantPlanNotFound):
        connection.rollback()
        raise HTTPException(status_code=404, detail="Evidence bundle was not found.") from None
    except ValueError as exc:
        connection.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        connection.rollback()
        raise HTTPException(status_code=503, detail="Tenant review storage is temporarily unavailable.") from None
    finally:
        connection.close()


@router.get("/professor/tenant/plans/{plan_id}/evidence/{bundle_step_id}/review")
def get_evidence_review(
    plan_id: str,
    bundle_step_id: str,
    request: Request,
    principal=Depends(require_verified_principal),
):
    """Return the latest reviewed bundle, or the original bundle before first review."""
    try:
        authorize_tenant_resource(principal, principal.tenant_id, {"evidence:review"})
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Evidence review access denied.") from None
    database_path = getattr(request.app.state, "tenant_data_path", None)
    if not database_path:
        raise HTTPException(status_code=503, detail="Tenant review storage is not configured.")
    connection = sqlite3.connect(database_path, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        initialize_tenant_evidence_review_schema(connection)
        step = TenantStepExecutionRepository(connection, principal).get_step(plan_id, bundle_step_id)
        if step.state != "succeeded" or step.capability != "research.evidence.bundle":
            raise ValueError("Only a completed evidence bundle can be retrieved for review.")
        original = _load_bundle(connection, principal.tenant_id, plan_id, bundle_step_id)
        row = connection.execute("""
          SELECT review_id,reviewer_id,reviewed_at,bundle_json
          FROM tenant_evidence_reviews
          WHERE tenant_id=? AND plan_id=? AND bundle_step_id=?
          ORDER BY review_id DESC LIMIT 1
        """, (principal.tenant_id, plan_id, bundle_step_id)).fetchone()
        if row is None:
            return {"status": "awaiting_review", "plan_id": plan_id,
                    "bundle_step_id": bundle_step_id, "revision": 0, "bundle": original}
        return {"status": "reviewed", "plan_id": plan_id,
                "bundle_step_id": bundle_step_id, "revision": row["review_id"],
                "reviewer_id": row["reviewer_id"], "reviewed_at": row["reviewed_at"],
                "bundle": json.loads(row["bundle_json"])}
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Evidence review access denied.") from None
    except TenantStepNotFound:
        raise HTTPException(status_code=404, detail="Evidence bundle was not found.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Tenant review storage is temporarily unavailable.") from None
    finally:
        connection.close()
