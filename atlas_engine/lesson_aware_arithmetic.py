"""A narrow, deterministic lesson-aware arithmetic specialist.

This is a real local lesson consumer for explicitly structured arithmetic aliases.
It is not a language model and does not infer rules from free-form lesson text.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from .executor import LocalTaskExecutor
from .lesson_contract import LessonAwareResult

MAX_ALIAS_CHARS = 80
MAX_EXPRESSION_CHARS = 256


class LessonAwareArithmeticExecutor:
    """Apply validated exact-match aliases, then use the bounded local math engine.

    A lesson is consumed only when its exact alias matches the complete task
    description. Ambiguous aliases fail closed. All substituted expressions
    still pass through LocalTaskExecutor's restricted AST arithmetic evaluator.
    """

    def __init__(self, executor: Any | None = None) -> None:
        self._executor = executor or LocalTaskExecutor(provider="local")

    @staticmethod
    def _validated_aliases(lessons: Any) -> list[tuple[str, str, str]]:
        if not isinstance(lessons, list):
            raise ValueError("Relevant lessons must be a list.")
        aliases: list[tuple[str, str, str]] = []
        for lesson in lessons:
            if not isinstance(lesson, Mapping):
                raise ValueError("Every relevant lesson must be an object.")
            if lesson.get("validated") is not True:
                continue
            if lesson.get("lesson_type") != "arithmetic_alias":
                continue
            lesson_id = lesson.get("id")
            application = lesson.get("application")
            if not isinstance(lesson_id, str) or not lesson_id.strip() or len(lesson_id) > 128:
                raise ValueError("Arithmetic alias lessons require a bounded ID.")
            if not isinstance(application, Mapping):
                raise ValueError("Arithmetic alias lessons require structured application data.")
            alias = application.get("alias")
            expression = application.get("expression")
            if not isinstance(alias, str) or not alias.strip() or len(alias) > MAX_ALIAS_CHARS:
                raise ValueError("Arithmetic alias must be a non-empty string of at most 80 characters.")
            if not isinstance(expression, str) or not expression.strip() or len(expression) > MAX_EXPRESSION_CHARS:
                raise ValueError("Arithmetic alias expression must be a bounded string.")
            aliases.append((lesson_id, alias.strip().casefold(), expression.strip()))
        return aliases

    def execute(self, task: dict[str, Any]) -> LessonAwareResult:
        if not isinstance(task, dict):
            raise ValueError("Task payload must be an object.")
        description = task.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError("Task description must be a non-empty string.")
        normalized = description.strip().casefold()
        matches = [
            (lesson_id, expression)
            for lesson_id, alias, expression in self._validated_aliases(
                copy.deepcopy(task.get("relevant_lessons", []))
            )
            if alias == normalized
        ]
        if len(matches) > 1:
            raise ValueError("Multiple validated lessons match this exact alias; execution is ambiguous.")
        delegated = copy.deepcopy(task)
        consumed: tuple[str, ...] = ()
        if matches:
            lesson_id, expression = matches[0]
            delegated["description"] = expression
            consumed = (lesson_id,)
        output = self._executor.execute(delegated)
        return LessonAwareResult(output=output, consumed_lesson_ids=consumed)
