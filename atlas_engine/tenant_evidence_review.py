"""Tenant-scoped, authenticated human review of completed evidence bundles.

Review records are append-only and never mutate immutable step execution results.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
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


class ProfessorQuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1000)


def _question_terms(value: str) -> set[str]:
    stop_words = {
        "about", "after", "also", "and", "are", "can", "does", "for", "from",
        "give", "have", "how", "into", "its", "more", "most", "not", "our",
        "please", "report", "say", "says", "show", "tell", "that", "the",
        "their", "there", "these", "this", "those", "what", "when", "where",
        "which", "who", "why", "with", "would", "you", "your",
    }
    return {
        token for token in re.findall(r"[a-z0-9]{3,}", value.casefold())
        if token not in stop_words
    }


def answer_report_question(report: dict[str, Any], question: str) -> dict[str, Any]:
    """Retrieve matching report records without generating new factual claims."""
    if not isinstance(report, dict) or report.get("report_type") != "professor_evidence_report":
        raise ValueError("A completed Professor evidence report is required.")
    if not isinstance(question, str) or not question.strip() or len(question) > 1000:
        raise ValueError("Question must contain 1 to 1000 characters.")
    summary = report.get("executive_summary")
    if not isinstance(summary, dict):
        raise ValueError("The Professor report summary is invalid.")

    terms = _question_terms(question)
    if not terms or terms.issubset({"summary", "overview", "overall", "counts", "conclusion"}):
        answer = (
            f"The report records {summary.get('claim_count', 0)} claims: "
            f"{summary.get('finding_count', 0)} findings, "
            f"{summary.get('challenge_count', 0)} challenges, "
            f"{summary.get('disagreement_count', 0)} disagreements and "
            f"{summary.get('evidence_gap_count', 0)} evidence gaps, across "
            f"{summary.get('source_count', 0)} sources. Confidence is not scored. "
            + str(summary.get("overall_conclusion", "No overall truth conclusion is drawn."))
        )
        return {
            "answer_type": "report_summary", "answer": answer, "matches": [],
            "basis": "summary", "items": [], "sources": [],
            "limitations": report.get("limitations", []),
            "mode": "deterministic_report_lookup",
        }

    matches = []
    section_terms = {
        "findings": {"finding", "findings", "supported"},
        "challenges": {"challenge", "challenges", "challenged"},
        "disagreements": {"disagreement", "disagreements", "conflict", "conflicts"},
        "evidence_gaps": {"gap", "gaps", "insufficient"},
    }
    for section in ("findings", "challenges", "disagreements", "evidence_gaps"):
        records = report.get(section, [])
        if not isinstance(records, list):
            continue
        requested_section_terms = terms.intersection(section_terms[section])
        for record in records:
            if not isinstance(record, dict):
                continue
            searchable = " ".join(str(record.get(key, "")) for key in
                                  ("claim_id", "claim", "status", "interpretation"))
            overlap = terms.intersection(_question_terms(searchable))
            if overlap or requested_section_terms:
                matches.append({
                    "section": section,
                    "claim_id": record.get("claim_id"),
                    "claim": record.get("claim"),
                    "status": record.get("status"),
                    "interpretation": record.get("interpretation", ""),
                    "supporting_sources": record.get("supporting_sources", []),
                    "challenging_sources": record.get("challenging_sources", []),
                    "mentioning_sources": record.get("mentioning_sources", []),
                    "matched_terms": sorted(overlap or requested_section_terms),
                })
    matches.sort(key=lambda item: (-len(item["matched_terms"]), str(item["claim_id"])))
    matches = matches[:5]
    if not matches:
        answer_type = "insufficient_report_match"
        answer = (
            "I cannot answer that from the completed report. No matching claim or "
            "evidence passage was found. A new research step or a more specific "
            "question may be needed."
        )
    else:
        references = []
        for item in matches:
            source_ids = list(dict.fromkeys(
                item["supporting_sources"] + item["challenging_sources"] +
                item["mentioning_sources"]
            ))
            references.append(
                f"{item['claim_id']} ({item['section']}; sources: "
                f"{', '.join(source_ids) if source_ids else 'none recorded'})"
            )
        answer_type = "matched_report_records"
        answer = (
            f"I found {len(matches)} relevant report record(s). These are report "
            "classifications based on supplied annotations, not independent "
            "verification. Relevant records: " + "; ".join(references) + "."
        )
    matched_sections = {item["section"] for item in matches}
    basis = next(iter(matched_sections)) if len(matched_sections) == 1 else "matched_records"
    source_ids = list(dict.fromkeys(
        source_id
        for item in matches
        for source_id in (
            item["supporting_sources"] + item["challenging_sources"] +
            item["mentioning_sources"]
        )
    ))
    source_records = report.get("sources", [])
    source_map = {
        item.get("source_id"): item for item in source_records
        if isinstance(item, dict) and item.get("source_id") in source_ids
    } if isinstance(source_records, list) else {}
    return {
        "answer_type": answer_type, "answer": answer, "matches": matches,
        "basis": basis, "items": matches,
        "sources": [source_map[item] for item in source_ids if item in source_map],
        "limitations": report.get("limitations", []),
        "mode": "deterministic_report_grounded",
        "tools_invoked": False, "execution_performed": False,
    }


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
        step = steps.get_step(plan_id, bundle_step_id)
        if step.state != "succeeded" or step.capability != "research.evidence.bundle":
            raise ValueError("Only a completed evidence bundle can be reviewed.")
        original = _load_bundle(connection, principal.tenant_id, plan_id, bundle_step_id)
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
        connection.rollback()
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


@router.post("/professor/tenant/plans/{plan_id}/ask")
def ask_professor_about_report(
    plan_id: str,
    payload: ProfessorQuestionInput,
    request: Request,
    principal=Depends(require_verified_principal),
):
    """Answer only from this tenant's completed report; this route is read-only."""
    database_path = getattr(request.app.state, "tenant_data_path", None)
    if not database_path:
        raise HTTPException(status_code=503, detail="Professor report storage is not configured.")
    connection = sqlite3.connect(database_path, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        steps = TenantStepExecutionRepository(connection, principal)
        records = steps.list_steps(plan_id)  # Enforces tenant boundary and steps:read.
        report_steps = [
            item for item in records
            if item.state == "succeeded"
            and item.capability == "research.professor.report"
            and isinstance(item.result, dict)
            and item.result.get("report_type") == "professor_evidence_report"
        ]
        if not report_steps:
            raise HTTPException(status_code=409, detail="No completed Professor report exists for this plan.")
        report = report_steps[-1].result
        try:
            return {
                "plan_id": plan_id,
                "report_step_id": report_steps[-1].step_id,
                **answer_report_question(report, payload.question),
            }
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
    except AuthorizationDenied:
        raise HTTPException(status_code=403, detail="Professor report access denied.") from None
    except TenantStepNotFound:
        raise HTTPException(status_code=404, detail="Plan was not found.") from None
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Professor report storage is temporarily unavailable.") from None
    finally:
        connection.close()


@router.get("/professor/evidence-review", include_in_schema=False)
def professor_evidence_review_ui():
    """Serve the browser evidence-review interface; all evidence data stays behind OIDC."""
    page = Path(__file__).resolve().parent.parent / "static" / "professor_evidence_review.html"
    return FileResponse(page, media_type="text/html")


@router.get("/professor/report", include_in_schema=False)
def professor_report_ui():
    """Serve the read-only, tenant-authenticated Professor report interface."""
    page = Path(__file__).resolve().parent.parent / "static" / "professor_report.html"
    return FileResponse(page, media_type="text/html")
