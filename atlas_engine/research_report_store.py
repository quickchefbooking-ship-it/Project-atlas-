"""Persist research reports only when evidence matches a completed run ledger."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import storage
from .research_evidence import ResearchReport, assess_report_integrity
from .research_orchestrator import ProfessorResearchOrchestrator


def _ensure_report_table() -> None:
    conn = storage.get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS professor_research_reports (
                run_id TEXT PRIMARY KEY,
                schema_version TEXT NOT NULL,
                report_json TEXT NOT NULL,
                integrity_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES professor_research_runs(run_id)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _run_evidence(run: dict) -> dict[str, dict]:
    evidence: dict[str, dict] = {}
    for step in run.get("steps", []):
        if step.get("status") != "completed":
            continue
        for item in (step.get("result") or {}).get("evidence", []):
            document_id = item.get("document_id")
            if not document_id:
                continue
            if document_id in evidence and evidence[document_id] != item:
                raise ValueError("Run evidence contains conflicting records for one document.")
            evidence[document_id] = item
    return evidence


def save_research_report(run_id: str, report: ResearchReport) -> dict:
    """Bind report provenance to this run; this does not assess semantic truth."""
    if not isinstance(run_id, str) or not run_id or len(run_id) > 160:
        raise ValueError("A valid research run ID is required.")
    if not isinstance(report, ResearchReport):
        raise TypeError("A validated ResearchReport is required.")
    run = ProfessorResearchOrchestrator.get_run(run_id)
    if run is None:
        raise ValueError("Research run was not found.")
    if run.get("status") != "completed":
        raise ValueError("A report can only be attached to a completed research run.")
    if report.task_id != run.get("task_id"):
        raise ValueError("Report task ID does not match the research run.")

    available = _run_evidence(run)
    for item in report.evidence:
        recorded = available.get(item.evidence_id)
        if recorded is None:
            raise ValueError("Report evidence must come from this run's persisted evidence.")
        expected = {
            "source_id": recorded.get("source_id"),
            "title": recorded.get("title"),
            "uri": recorded.get("uri"),
            "content_sha256": recorded.get("content_sha256"),
            "trust_level": recorded.get("trust_level"),
            "review_state": recorded.get("review_state"),
        }
        supplied = {
            "source_id": item.source_id,
            "title": item.title,
            "uri": item.uri,
            "content_sha256": item.content_sha256,
            "trust_level": item.trust_level,
            "review_state": item.review_state,
        }
        if expected != supplied:
            raise ValueError("Report evidence metadata does not match the run ledger.")

    integrity = assess_report_integrity(report)
    report_json = report.model_dump_json()
    integrity_json = json.dumps(integrity, sort_keys=True, separators=(",", ":"))
    created_at = datetime.now(timezone.utc).isoformat()
    _ensure_report_table()
    conn = storage.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO professor_research_reports
               (run_id, schema_version, report_json, integrity_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (run_id, report.schema_version, report_json, integrity_json, created_at),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"run_id": run_id, "task_id": report.task_id,
            "schema_version": report.schema_version, "integrity": integrity,
            "created_at": created_at}


def get_research_report(run_id: str) -> dict | None:
    _ensure_report_table()
    conn = storage.get_connection()
    try:
        row = conn.execute(
            """SELECT schema_version, report_json, integrity_json, created_at
               FROM professor_research_reports WHERE run_id = ?""", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return {"run_id": run_id, "schema_version": row["schema_version"],
                "report": json.loads(row["report_json"]),
                "integrity": json.loads(row["integrity_json"]),
                "created_at": row["created_at"]}
    finally:
        conn.close()
