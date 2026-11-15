"""Descriptive analysis for controlled lesson-use experiments.

This module analyses already-collected paired observations. It does not run
executors, randomise treatment, establish causality, or prove semantic lesson use.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


MAX_EXPERIMENT_PAIRS = 10_000
MIN_PAIRS_FOR_SIGNAL = 10


def analyse_paired_lesson_experiment(
    observations: Sequence[Mapping[str, Any]],
    *,
    experiment_id: str,
    criteria_version: str,
) -> dict[str, Any]:
    """Compare baseline and lesson-enabled outcomes on identical case IDs.

    Each case must have exactly one baseline and one treatment observation.
    Outcomes are binary pass/fail values scored against the same criteria version.
    The returned difference is descriptive only; no significance or causal claim
    is made, and missing/invalid pairs are rejected rather than silently dropped.
    """
    for name, value in (("experiment_id", experiment_id), ("criteria_version", criteria_version)):
        if not isinstance(value, str) or not value.strip() or len(value) > 128:
            raise ValueError(f"{name} must be a non-empty string of at most 128 characters.")
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        raise ValueError("Observations must be a sequence of records.")
    if len(observations) > MAX_EXPERIMENT_PAIRS * 2:
        raise ValueError("Experiment exceeds the supported observation limit.")

    pairs: dict[str, dict[str, bool]] = {}
    for row in observations:
        if not isinstance(row, Mapping):
            raise ValueError("Every experiment observation must be an object.")
        case_id = row.get("case_id")
        arm = row.get("arm")
        passed = row.get("passed")
        version = row.get("criteria_version")
        if not isinstance(case_id, str) or not case_id.strip() or len(case_id) > 128:
            raise ValueError("Every observation requires a bounded case_id.")
        if arm not in ("baseline", "lesson_enabled"):
            raise ValueError("Observation arm must be baseline or lesson_enabled.")
        if type(passed) is not bool:
            raise ValueError("Observation passed must be a boolean.")
        if version != criteria_version:
            raise ValueError("All observations must use the requested criteria version.")
        pair = pairs.setdefault(case_id, {})
        if arm in pair:
            raise ValueError("Each case must have exactly one observation per arm.")
        pair[arm] = passed

    if any(set(pair) != {"baseline", "lesson_enabled"} for pair in pairs.values()):
        raise ValueError("Every case must have both baseline and lesson-enabled observations.")
    if not pairs:
        raise ValueError("At least one complete paired case is required.")

    total = len(pairs)
    baseline_passes = sum(pair["baseline"] for pair in pairs.values())
    treatment_passes = sum(pair["lesson_enabled"] for pair in pairs.values())
    improved = sum(not pair["baseline"] and pair["lesson_enabled"] for pair in pairs.values())
    regressed = sum(pair["baseline"] and not pair["lesson_enabled"] for pair in pairs.values())
    unchanged = total - improved - regressed

    baseline_rate = baseline_passes / total
    treatment_rate = treatment_passes / total
    difference = treatment_rate - baseline_rate
    if total < MIN_PAIRS_FOR_SIGNAL:
        status = "insufficient_data"
    elif difference > 0:
        status = "descriptive_positive_signal"
    elif difference < 0:
        status = "descriptive_negative_signal"
    else:
        status = "no_descriptive_difference"

    return {
        "experiment_id": experiment_id,
        "criteria_version": criteria_version,
        "status": status,
        "pairs": total,
        "baseline": {"passed": baseline_passes, "total": total, "pass_rate": round(baseline_rate, 4)},
        "lesson_enabled": {"passed": treatment_passes, "total": total, "pass_rate": round(treatment_rate, 4)},
        "paired_outcomes": {"improved": improved, "regressed": regressed, "unchanged": unchanged},
        "absolute_pass_rate_difference": round(difference, 4),
        "interpretation": (
            "Descriptive paired result only. It does not establish causality, statistical significance, "
            "semantic lesson consumption, or generalisation beyond these cases."
        ),
    }
