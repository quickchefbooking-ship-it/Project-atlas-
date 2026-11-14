import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from .storage import save_lesson, search_validated_lessons


MAX_LESSON_EVIDENCE_BYTES = 16 * 1024
MAX_LESSON_EVIDENCE_DEPTH = 64


def _validate_json_value(
    value: Any,
    path: str = "evidence",
    *,
    _active_containers: set[int] | None = None,
    _depth: int = 0,
) -> None:
    """Reject non-JSON values, cycles and excessive nesting before serialisation."""
    if _depth > MAX_LESSON_EVIDENCE_DEPTH:
        raise ValueError(
            f"{path} exceeds the maximum nesting depth of {MAX_LESSON_EVIDENCE_DEPTH}."
        )
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number.")
        return

    if isinstance(value, (list, dict)):
        if _active_containers is None:
            _active_containers = set()
        container_id = id(value)
        if container_id in _active_containers:
            raise ValueError(f"{path} contains a circular reference.")
        _active_containers.add(container_id)
        try:
            if isinstance(value, list):
                for index, item in enumerate(value):
                    _validate_json_value(
                        item,
                        f"{path}[{index}]",
                        _active_containers=_active_containers,
                        _depth=_depth + 1,
                    )
            else:
                for key, item in value.items():
                    if not isinstance(key, str):
                        raise ValueError(f"{path} contains a non-string object key.")
                    _validate_json_value(
                        item,
                        f"{path}.{key}",
                        _active_containers=_active_containers,
                        _depth=_depth + 1,
                    )
        finally:
            _active_containers.remove(container_id)
        return

    raise ValueError(f"{path} contains a value that is not JSON-compatible.")


class LearningMemory:
    def __init__(self):
        pass

    @staticmethod
    def _keywords(text: str) -> set[str]:
        return {word.lower() for word in re.findall(r"[a-zA-Z0-9_]+", text) if len(word) > 2}

    @staticmethod
    def save_lesson_for_task(task_id: str, lesson_type: str, summary: str, source: str, evidence: Dict[str, Any], validated: bool = False) -> Dict[str, Any]:
        """Persist a lesson as unvalidated; validation is a separate review decision.

        The legacy argument remains for call compatibility, but callers cannot
        self-certify a lesson at creation time. A future authenticated reviewer
        workflow must perform that transition after checking the evidence.
        """
        if validated is not False:
            raise ValueError(
                "Lessons cannot be marked validated at creation; explicit review is required."
            )
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("A task ID is required to associate the lesson with its outcome.")
        if not isinstance(lesson_type, str) or not lesson_type.strip():
            raise ValueError("A lesson type is required.")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("A lesson summary is required.")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("A lesson source is required.")
        if not isinstance(evidence, dict):
            raise ValueError("Lesson evidence must be an object.")

        _validate_json_value(evidence)
        if lesson_type.strip() == "arithmetic_alias":
            application = evidence.get("application")
            if not isinstance(application, dict) or set(application) != {"alias", "expression"}:
                raise ValueError(
                    "Arithmetic alias lessons require application with only alias and expression."
                )
            alias = application.get("alias")
            expression = application.get("expression")
            if (
                not isinstance(alias, str) or not alias.strip() or len(alias) > 80
                or not isinstance(expression, str) or not expression.strip() or len(expression) > 256
            ):
                raise ValueError("Arithmetic alias application fields are invalid.")
        try:
            evidence_json = json.dumps(
                evidence, sort_keys=True, allow_nan=False, separators=(",", ":")
            )
            evidence_size = len(evidence_json.encode("utf-8"))
        except (TypeError, ValueError, OverflowError, UnicodeError) as exc:
            raise ValueError("Lesson evidence must contain only finite JSON values.") from exc
        if evidence_size > MAX_LESSON_EVIDENCE_BYTES:
            raise ValueError(
                f"Lesson evidence exceeds the {MAX_LESSON_EVIDENCE_BYTES:,}-byte limit."
            )

        payload = {
            "id": f"lesson-{uuid4().hex}",
            "task_id": task_id.strip(),
            "lesson_type": lesson_type.strip(),
            "summary": summary.strip(),
            "source": source.strip(),
            "evidence_json": evidence_json,
            "validated": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        save_lesson(payload)
        return payload

    @staticmethod
    def get_relevant_lessons(task_description: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not isinstance(task_description, str) or not task_description.strip():
            return []
        if not isinstance(limit, int) or limit < 1 or limit > 50:
            raise ValueError("Lesson retrieval limit must be between 1 and 50.")
        incoming_keywords = sorted(LearningMemory._keywords(task_description))[:64]
        # Rank across the full validated corpus rather than truncating candidates to the 100 newest
        # records, so older useful lessons remain discoverable as memory grows.
        lessons = search_validated_lessons(incoming_keywords, limit=limit)
        runtime_lessons: list[Dict[str, Any]] = []
        for lesson in lessons:
            # SQLite returns integer booleans. Normalize the validated marker so
            # specialist contracts receive one stable representation.
            lesson["validated"] = lesson.get("validated") in (1, True)
            if lesson.get("lesson_type") == "arithmetic_alias":
                try:
                    evidence = json.loads(lesson.get("evidence_json") or "{}")
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError("Validated arithmetic alias lesson evidence is malformed.") from exc
                application = evidence.get("application") if isinstance(evidence, dict) else None
                if not isinstance(application, dict):
                    raise ValueError("Validated arithmetic alias lesson requires application evidence.")
                if set(application) != {"alias", "expression"}:
                    raise ValueError("Arithmetic alias application must contain only alias and expression.")
                alias = application.get("alias")
                expression = application.get("expression")
                if (
                    not isinstance(alias, str) or not alias.strip() or len(alias) > 80
                    or not isinstance(expression, str) or not expression.strip() or len(expression) > 256
                ):
                    raise ValueError("Arithmetic alias application fields are invalid.")
                lesson["application"] = {"alias": alias.strip(), "expression": expression.strip()}
            runtime_lessons.append(lesson)
        return runtime_lessons

    @staticmethod
    def get_recent_task_history(limit: int = 20) -> List[Dict[str, Any]]:
        from .storage import list_tasks
        return list_tasks(limit)
