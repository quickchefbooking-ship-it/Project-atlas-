"""Verifiable contract for lesson-aware executor receipts.

An executor explicitly reports which validated lesson IDs it claims to have
consumed. Professor validates the receipt against the exact supplied context
and atomically persists accepted IDs with the task outcome. This is auditable
attribution, not cryptographic proof of semantic use or evidence of improvement.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


MAX_CONSUMED_LESSON_IDS = 50


@dataclass(frozen=True)
class LessonAwareResult:
    """Execution result plus an explicit, immutable lesson-consumption receipt."""

    output: Mapping[str, Any]
    consumed_lesson_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.output, Mapping):
            raise ValueError("Lesson-aware output must be an object.")
        if not isinstance(self.consumed_lesson_ids, tuple):
            raise ValueError("Consumed lesson IDs must be an immutable tuple.")
        if len(self.consumed_lesson_ids) > MAX_CONSUMED_LESSON_IDS:
            raise ValueError("Consumed lesson receipt exceeds the supported limit.")
        if any(
            not isinstance(item, str) or not item.strip() or len(item) > 256
            for item in self.consumed_lesson_ids
        ):
            raise ValueError("Every consumed lesson ID must be a non-empty bounded string.")
        if len(set(self.consumed_lesson_ids)) != len(self.consumed_lesson_ids):
            raise ValueError("Consumed lesson IDs must be unique.")


def validate_lesson_aware_result(
    result: Any,
    supplied_lessons: list[Mapping[str, Any]],
) -> LessonAwareResult:
    """Accept only receipts referring to lessons supplied as validated context.

    The executor's receipt is an auditable claim, not cryptographic proof that
    semantic reasoning used a lesson. The later executor implementation must
    define and test its own consumption semantics before this can be treated as
    stronger evidence.
    """
    if not isinstance(result, LessonAwareResult):
        raise ValueError("Lesson-aware executors must return a LessonAwareResult.")
    if not isinstance(supplied_lessons, list):
        raise ValueError("Supplied lesson context must be a list.")

    eligible_ids: set[str] = set()
    for lesson in supplied_lessons:
        if not isinstance(lesson, Mapping):
            raise ValueError("Supplied lesson context contains an invalid record.")
        lesson_id = lesson.get("id")
        validated = lesson.get("validated")
        if (
            isinstance(lesson_id, str)
            and lesson_id.strip()
            and validated in (1, True)
            and type(validated) in (int, bool)
        ):
            eligible_ids.add(lesson_id)

    unknown = set(result.consumed_lesson_ids) - eligible_ids
    if unknown:
        raise ValueError("Lesson receipt references an ID outside validated supplied context.")
    return result
