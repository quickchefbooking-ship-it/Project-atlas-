"""Offline paired runner for lesson-use experiments.

This is an explicitly injected, in-process test harness. It has no persistence,
network access, task-queue integration, or capability execution. Results are
descriptive observations, not proof of causal improvement.
"""
from __future__ import annotations

import copy
import random
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .evaluator import Evaluator
from .lesson_contract import LessonAwareResult, validate_lesson_aware_result
from .lesson_experiment import analyse_paired_lesson_experiment


MAX_EXPERIMENT_CASES = 250
MAX_CRITERIA_VERSION_CHARS = 128


def _invoke(executor: Any, payload: dict[str, Any]) -> Any:
    if callable(executor):
        return executor(payload)
    execute = getattr(executor, "execute", None)
    if callable(execute):
        return execute(payload)
    raise TypeError("Executor must be callable or expose execute(payload).")


class OfflineLessonExperimentRunner:
    """Run matched cases through injected baseline and lesson-aware executors.

    The caller supplies both executors and the validated lesson context. Each
    arm receives a deep-copied identical task input and criteria. Arm order is
    shuffled using a local seeded PRNG; this is order balancing only, not
    blinding or full experimental randomisation.
    """

    def __init__(
        self,
        baseline_executor: Any,
        lesson_executor: Any,
        *,
        evaluator: Any = Evaluator,
    ) -> None:
        self._baseline_executor = baseline_executor
        self._lesson_executor = lesson_executor
        self._evaluator = evaluator

    def run(
        self,
        cases: Sequence[Mapping[str, Any]],
        *,
        experiment_id: str,
        criteria_version: str,
        validated_lessons: Sequence[Mapping[str, Any]],
        seed: int = 0,
    ) -> dict[str, Any]:
        if not isinstance(experiment_id, str) or not experiment_id.strip() or len(experiment_id) > 128:
            raise ValueError("experiment_id must be a non-empty string of at most 128 characters.")
        if not isinstance(criteria_version, str) or not criteria_version.strip() or len(criteria_version) > MAX_CRITERIA_VERSION_CHARS:
            raise ValueError("criteria_version must be a non-empty string of at most 128 characters.")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed must be an integer.")
        if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)) or not 1 <= len(cases) <= MAX_EXPERIMENT_CASES:
            raise ValueError(f"cases must contain between 1 and {MAX_EXPERIMENT_CASES} records.")
        if not isinstance(validated_lessons, Sequence) or isinstance(validated_lessons, (str, bytes)):
            raise ValueError("validated_lessons must be a sequence.")

        lessons = copy.deepcopy(list(validated_lessons))
        lesson_ids: set[str] = set()
        for lesson in lessons:
            if not isinstance(lesson, Mapping):
                raise ValueError("Every lesson must be an object.")
            lesson_id = lesson.get("id")
            if not isinstance(lesson_id, str) or not lesson_id.strip() or lesson.get("validated") not in (True, 1):
                raise ValueError("Only identified, validated lessons may enter the treatment arm.")
            if type(lesson.get("validated")) not in (bool, int):
                raise ValueError("Only identified, validated lessons may enter the treatment arm.")
            if lesson_id in lesson_ids:
                raise ValueError("Validated lesson IDs must be unique.")
            lesson_ids.add(lesson_id)

        case_ids: set[str] = set()
        normalized_cases: list[dict[str, Any]] = []
        for case in cases:
            if not isinstance(case, Mapping):
                raise ValueError("Every case must be an object.")
            case_id = case.get("case_id")
            task_input = case.get("task_input")
            criteria = case.get("success_criteria")
            if not isinstance(case_id, str) or not case_id.strip() or len(case_id) > 128:
                raise ValueError("Every case requires a bounded case_id.")
            if case_id in case_ids:
                raise ValueError("case_id values must be unique.")
            if not isinstance(task_input, Mapping):
                raise ValueError("Every case requires task_input as an object.")
            if not isinstance(criteria, (Mapping, list)):
                raise ValueError("Every case requires success_criteria as an object or array.")
            case_ids.add(case_id)
            normalized_cases.append({
                "case_id": case_id,
                "task_input": copy.deepcopy(dict(task_input)),
                "success_criteria": copy.deepcopy(criteria),
            })

        rng = random.Random(seed)
        observations: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        for case in normalized_cases:
            arms = ["baseline", "lesson_enabled"]
            rng.shuffle(arms)
            arm_results: dict[str, dict[str, Any]] = {}
            for arm in arms:
                treatment = arm == "lesson_enabled"
                payload = {
                    "case_id": case["case_id"],
                    "task_input": copy.deepcopy(case["task_input"]),
                    "success_criteria": copy.deepcopy(case["success_criteria"]),
                    "criteria_version": criteria_version,
                    "relevant_lessons": copy.deepcopy(lessons) if treatment else [],
                }
                raw = _invoke(
                    self._lesson_executor if treatment else self._baseline_executor,
                    payload,
                )
                if treatment:
                    receipt = validate_lesson_aware_result(raw, list(payload["relevant_lessons"]))
                    output = copy.deepcopy(dict(receipt.output))
                    consumed_ids = list(receipt.consumed_lesson_ids)
                else:
                    if isinstance(raw, LessonAwareResult):
                        raise ValueError("Baseline executor must not return a lesson-use receipt.")
                    if not isinstance(raw, Mapping):
                        raise ValueError("Baseline executor must return an output object.")
                    output = copy.deepcopy(dict(raw))
                    consumed_ids = []
                evaluation = self._evaluator.evaluate(output, copy.deepcopy(case["success_criteria"]))
                if type(evaluation.get("passed")) is not bool:
                    raise ValueError("Evaluator must return a boolean passed outcome.")
                observation = {
                    "case_id": case["case_id"],
                    "arm": arm,
                    "passed": evaluation["passed"],
                    "criteria_version": criteria_version,
                }
                observations.append(observation)
                arm_results[arm] = {
                    "output": output,
                    "passed": evaluation["passed"],
                    "score": evaluation.get("score"),
                    "consumed_lesson_ids": consumed_ids,
                }
            evidence.append({"case_id": case["case_id"], "arms": arm_results})

        report = analyse_paired_lesson_experiment(
            observations,
            experiment_id=experiment_id,
            criteria_version=criteria_version,
        )
        return {
            "report": report,
            "observations": observations,
            "evidence": evidence,
            "execution_mode": "offline_in_process_only",
            "arm_order_seed": seed,
            "limitations": [
                "No external model, API, network, task queue, or capability was invoked.",
                "Seeded arm ordering is not blinding or full experimental randomisation.",
                "Lesson receipts are executor declarations, not proof of semantic use.",
                "Descriptive outcomes do not establish causality, statistical significance, or generalisation.",
                "Results are returned in memory and are not durably persisted.",
            ],
        }
