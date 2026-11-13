"""Persisted, bounded orchestration for read-only Professor research plans.

This service accepts a plan and scopes from trusted application code. It is not an
HTTP endpoint and does not infer identity, grant scopes, call a language model, or
execute model-generated code.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from . import storage
from .model_provider import ProposedCapabilityCall
from .research_capability_executor import ResearchCapabilityExecutor
from .research_capabilities import validate_research_capability_call
from .research_plan import ResearchPlan


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_research_tables() -> None:
    conn = storage.get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS professor_research_runs (
                run_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('planned','running','completed','failed')),
                started_at TEXT NOT NULL,
                finished_at TEXT,
                error_type TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_professor_research_runs_task
            ON professor_research_runs(task_id, started_at DESC)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS professor_research_steps (
                run_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                capability_id TEXT NOT NULL,
                capability_version TEXT NOT NULL,
                arguments_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','running','completed','failed','skipped')),
                started_at TEXT,
                finished_at TEXT,
                result_json TEXT,
                error_type TEXT,
                PRIMARY KEY(run_id, step_id),
                FOREIGN KEY(run_id) REFERENCES professor_research_runs(run_id)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _ordered_steps(plan: ResearchPlan):
    by_id = {step.step_id: step for step in plan.steps}
    ordered = []
    visited = set()
    while len(ordered) < len(plan.steps):
        ready = [
            step for step in plan.steps
            if step.step_id not in visited and set(step.depends_on) <= visited
        ]
        if not ready:
            raise ValueError("Research plan dependency graph cannot be ordered.")
        for step in ready:
            ordered.append(step)
            visited.add(step.step_id)
    return ordered


def _evidence_summary(result: dict[str, Any]) -> dict[str, Any]:
    """Persist traceable references, not duplicate potentially large source bodies."""
    refs = []
    for item in result.get("evidence", []):
        if not isinstance(item, dict):
            continue
        citation = item.get("citation") if isinstance(item.get("citation"), dict) else {}
        refs.append({
            "document_id": item.get("document_id") or item.get("id") or citation.get("document_id"),
            "source_id": item.get("source_id") or citation.get("source_id"),
            "title": item.get("title") or citation.get("title"),
            "uri": item.get("uri") or citation.get("url"),
            "content_sha256": item.get("content_sha256") or citation.get("content_sha256"),
            "trust_level": item.get("trust_level") or citation.get("trust_level"),
            "review_state": item.get("review_state"),
            "score": item.get("score"),
            "snippet": item.get("snippet"),
            "matched_terms": item.get("matched_terms"),
        })
    return {
        "capability_id": result.get("capability_id"),
        "capability_version": result.get("capability_version"),
        "evidence_state": result.get("evidence_state"),
        "evidence": refs,
    }


class ProfessorResearchOrchestrator:
    """Execute a validated plan sequentially and persist a replayable audit trail."""

    def __init__(self, executor: ResearchCapabilityExecutor | None = None):
        self.executor = executor or ResearchCapabilityExecutor()
        _ensure_research_tables()

    def run(
        self,
        plan: ResearchPlan,
        *,
        granted_scopes: frozenset[str],
    ) -> dict[str, Any]:
        if not isinstance(plan, ResearchPlan):
            raise TypeError("A validated ResearchPlan is required.")
        if not isinstance(granted_scopes, frozenset) or any(
            not isinstance(scope, str) for scope in granted_scopes
        ):
            raise TypeError("Trusted immutable capability scopes are required.")

        ordered = _ordered_steps(plan)
        # Validate every capability and its arguments before persisting or executing
        # any step. An invalid later step must not leave a partially executed run.
        for step in ordered:
            definition, _arguments = validate_research_capability_call(
                self.executor.registry,
                ProposedCapabilityCall(
                    capability_id=step.capability_id,
                    capability_version=step.capability_version,
                    arguments=step.arguments,
                ),
            )
            missing_scopes = set(definition.required_scopes) - set(granted_scopes)
            if missing_scopes:
                raise PermissionError(
                    "The caller does not hold the required research capability scope."
                )

        run_id = f"research-{uuid4().hex}"
        started_at = _now()
        plan_json = plan.model_dump_json()
        conn = storage.get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """INSERT INTO professor_research_runs
                   (run_id, task_id, schema_version, plan_json, status, started_at)
                   VALUES (?, ?, ?, ?, 'running', ?)""",
                (run_id, plan.task_id, plan.schema_version, plan_json, started_at),
            )
            for ordinal, step in enumerate(ordered):
                conn.execute(
                    """INSERT INTO professor_research_steps
                       (run_id, step_id, ordinal, capability_id, capability_version,
                        arguments_json, status)
                       VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
                    (
                        run_id, step.step_id, ordinal, step.capability_id,
                        step.capability_version,
                        json.dumps(step.arguments, sort_keys=True, separators=(",", ":")),
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        deadline = time.monotonic() + plan.max_duration_seconds
        completed: list[dict[str, Any]] = []
        failed_step: str | None = None
        failure_type: str | None = None

        for step in ordered:
            if time.monotonic() >= deadline:
                failed_step = step.step_id
                failure_type = "ResearchRunDeadlineExceeded"
                self._finish_step(run_id, step.step_id, "failed", error_type=failure_type)
                break

            self._mark_step_running(run_id, step.step_id)
            try:
                result = self.executor.execute(
                    ProposedCapabilityCall(
                        capability_id=step.capability_id,
                        capability_version=step.capability_version,
                        arguments=step.arguments,
                    ),
                    granted_scopes=granted_scopes,
                )
                summary = _evidence_summary(result)
                # Keep the audit record bounded. Source content is retained in the
                # Source Division store, referenced by ID and SHA-256 digest.
                encoded = json.dumps(summary, sort_keys=True, separators=(",", ":"))
                if len(encoded) > 100_000:
                    raise ValueError("Research evidence reference summary exceeded its storage limit.")
                self._finish_step(run_id, step.step_id, "completed", result_json=encoded)
                completed.append({"step_id": step.step_id, **summary})
            except Exception as exc:
                failed_step = step.step_id
                failure_type = type(exc).__name__
                self._finish_step(run_id, step.step_id, "failed", error_type=failure_type)
                break

        if failed_step is not None:
            # Never execute dependent or subsequent steps after a failed capability.
            completed_ids = {item["step_id"] for item in completed}
            for step in ordered:
                if step.step_id not in completed_ids and step.step_id != failed_step:
                    self._finish_step(run_id, step.step_id, "skipped", error_type="PriorStepFailed")
            status = "failed"
        else:
            status = "completed"

        finished_at = _now()
        conn = storage.get_connection()
        try:
            conn.execute(
                """UPDATE professor_research_runs
                   SET status = ?, finished_at = ?, error_type = ?
                   WHERE run_id = ? AND status = 'running'""",
                (status, finished_at, failure_type, run_id),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "run_id": run_id,
            "task_id": plan.task_id,
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "completed_steps": completed,
            "failed_step": failed_step,
            "error_type": failure_type,
        }

    @staticmethod
    def _mark_step_running(run_id: str, step_id: str) -> None:
        conn = storage.get_connection()
        try:
            cursor = conn.execute(
                """UPDATE professor_research_steps
                   SET status = 'running', started_at = ?
                   WHERE run_id = ? AND step_id = ? AND status = 'pending'""",
                (_now(), run_id, step_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Research step state transition was not accepted.")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _finish_step(
        run_id: str,
        step_id: str,
        status: str,
        *,
        result_json: str | None = None,
        error_type: str | None = None,
    ) -> None:
        if status not in {"completed", "failed", "skipped"}:
            raise ValueError("Unsupported research step terminal state.")
        conn = storage.get_connection()
        try:
            cursor = conn.execute(
                """UPDATE professor_research_steps
                   SET status = ?, finished_at = ?, result_json = ?, error_type = ?
                   WHERE run_id = ? AND step_id = ? AND status IN ('pending','running')""",
                (status, _now(), result_json, error_type, run_id, step_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Research step terminal state was not accepted.")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def recover_interrupted_runs(*, stale_before: str) -> dict[str, Any]:
        """Mark old in-flight runs failed; never resume or re-execute their steps.

        The caller must choose a conservative, timezone-aware cutoff. This method
        is explicit (not called automatically at startup) to avoid classifying a
        slow but healthy run as abandoned.
        """
        try:
            cutoff = datetime.fromisoformat(stale_before.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise ValueError("stale_before must be a timezone-aware ISO-8601 timestamp.") from exc
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("stale_before must be a timezone-aware ISO-8601 timestamp.")
        cutoff_text = cutoff.astimezone(timezone.utc).isoformat()
        recovered_at = _now()
        conn = storage.get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """SELECT run_id FROM professor_research_runs
                   WHERE status = 'running' AND started_at < ?""",
                (cutoff_text,),
            ).fetchall()
            run_ids = [row["run_id"] for row in rows]
            for run_id in run_ids:
                conn.execute(
                    """UPDATE professor_research_steps
                       SET status = CASE
                           WHEN status = 'running' THEN 'failed'
                           WHEN status = 'pending' THEN 'skipped'
                           ELSE status END,
                           finished_at = CASE
                           WHEN status IN ('running','pending') THEN ?
                           ELSE finished_at END,
                           error_type = CASE
                           WHEN status = 'running' THEN 'InterruptedRunRecovered'
                           WHEN status = 'pending' THEN 'PriorStepInterrupted'
                           ELSE error_type END
                       WHERE run_id = ? AND status IN ('running','pending')""",
                    (recovered_at, run_id),
                )
                conn.execute(
                    """UPDATE professor_research_runs
                       SET status = 'failed', finished_at = ?,
                           error_type = 'InterruptedRunRecovered'
                       WHERE run_id = ? AND status = 'running'""",
                    (recovered_at, run_id),
                )
            conn.commit()
            return {
                "recovered_run_ids": run_ids,
                "recovered_count": len(run_ids),
                "recovery_policy": "fail_without_resume",
                "recovered_at": recovered_at,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def get_run(run_id: str) -> dict[str, Any] | None:
        _ensure_research_tables()
        conn = storage.get_connection()
        try:
            run = conn.execute(
                "SELECT * FROM professor_research_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if run is None:
                return None
            steps = conn.execute(
                """SELECT step_id, ordinal, capability_id, capability_version,
                          arguments_json, status, started_at, finished_at,
                          result_json, error_type
                   FROM professor_research_steps WHERE run_id = ? ORDER BY ordinal""",
                (run_id,),
            ).fetchall()
            result = dict(run)
            result["plan"] = json.loads(result.pop("plan_json"))
            result["steps"] = [
                {
                    **dict(step),
                    "arguments": json.loads(step["arguments_json"]),
                    "result": json.loads(step["result_json"]) if step["result_json"] else None,
                }
                for step in steps
            ]
            for step in result["steps"]:
                step.pop("arguments_json", None)
                step.pop("result_json", None)
            return result
        finally:
            conn.close()
