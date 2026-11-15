"""Insert-only persistence for privacy-minimised offline lesson experiments."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections.abc import Mapping
from typing import Any

from . import storage

MAX_RECORD_BYTES = 1_000_000


def _canonical_json(value: Any) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Experiment records must contain finite JSON-compatible values.") from exc
    if len(encoded.encode("utf-8")) > MAX_RECORD_BYTES:
        raise ValueError("Experiment record exceeds the 1 MB storage limit.")
    return encoded


def _project_result(result: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        raise ValueError("Experiment result must be an object.")
    report = result.get("report")
    observations = result.get("observations")
    evidence = result.get("evidence")
    if not isinstance(report, Mapping) or not isinstance(observations, list) or not isinstance(evidence, list):
        raise ValueError("Experiment result is missing its report, observations, or evidence.")
    experiment_id = report.get("experiment_id")
    criteria_version = report.get("criteria_version")
    if not isinstance(experiment_id, str) or not experiment_id.strip() or len(experiment_id) > 128:
        raise ValueError("Experiment ID must be a non-empty string of at most 128 characters.")
    if not isinstance(criteria_version, str) or not criteria_version.strip() or len(criteria_version) > 128:
        raise ValueError("Criteria version must be a non-empty string of at most 128 characters.")
    if result.get("execution_mode") != "offline_in_process_only":
        raise ValueError("Only offline in-process experiment results may be stored.")
    seed = result.get("arm_order_seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("Experiment arm-order seed must be an integer.")

    # Deliberately omit raw executor outputs, task inputs, and lesson text.
    compact_evidence = []
    for case in evidence:
        if not isinstance(case, Mapping) or not isinstance(case.get("case_id"), str):
            raise ValueError("Experiment evidence contains an invalid case.")
        arms = case.get("arms")
        if not isinstance(arms, Mapping) or set(arms) != {"baseline", "lesson_enabled"}:
            raise ValueError("Each evidence case must contain both experiment arms.")
        compact_arms = {}
        for arm_name in ("baseline", "lesson_enabled"):
            arm = arms[arm_name]
            if not isinstance(arm, Mapping) or type(arm.get("passed")) is not bool:
                raise ValueError("Experiment arm evidence is invalid.")
            score = arm.get("score")
            if score is not None and (
                isinstance(score, bool) or not isinstance(score, (int, float))
                or not math.isfinite(float(score))
            ):
                raise ValueError("Experiment arm score must be a finite number or null.")
            consumed = arm.get("consumed_lesson_ids", [])
            if not isinstance(consumed, list) or any(
                not isinstance(item, str) or not item or len(item) > 128 for item in consumed
            ):
                raise ValueError("Consumed lesson IDs must be bounded strings.")
            compact_arms[arm_name] = {
                "passed": arm["passed"],
                "score": score,
                "consumed_lesson_ids": consumed,
            }
        compact_evidence.append({"case_id": case["case_id"], "arms": compact_arms})

    payload = {
        "report": dict(report),
        "observations": observations,
        "evidence": compact_evidence,
        "execution_mode": "offline_in_process_only",
        "arm_order_seed": seed,
    }
    canonical = _canonical_json(payload)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "experiment_id": experiment_id,
        "criteria_version": criteria_version,
        "payload_json": canonical,
        "sha256": digest,
    }


def save_lesson_experiment_run(result: Mapping[str, Any]) -> dict[str, Any]:
    """Persist a completed run once; duplicate IDs are rejected, never overwritten."""
    record = _project_result(result)
    created_at = storage.now_isoformat()
    conn = storage.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO lesson_experiment_runs
               (experiment_id, criteria_version, execution_mode, arm_order_seed,
                payload_json, payload_sha256, created_at)
               VALUES (?, ?, 'offline_in_process_only', ?, ?, ?, ?)""",
            (
                record["experiment_id"], record["criteria_version"],
                result["arm_order_seed"], record["payload_json"],
                record["sha256"], created_at,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("An experiment run with this ID already exists.") from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return get_lesson_experiment_run(record["experiment_id"])


def get_lesson_experiment_run(experiment_id: str) -> dict[str, Any] | None:
    if not isinstance(experiment_id, str) or not experiment_id.strip() or len(experiment_id) > 128:
        raise ValueError("Experiment ID must be a non-empty string of at most 128 characters.")
    conn = storage.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM lesson_experiment_runs WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    payload_json = row["payload_json"]
    digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    if digest != row["payload_sha256"]:
        raise ValueError("Stored experiment record failed its integrity check.")
    return {
        "experiment_id": row["experiment_id"],
        "criteria_version": row["criteria_version"],
        "execution_mode": row["execution_mode"],
        "arm_order_seed": row["arm_order_seed"],
        "created_at": row["created_at"],
        "payload_sha256": digest,
        **json.loads(payload_json),
    }
