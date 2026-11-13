import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from .storage import save_lesson, search_validated_lessons


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

        try:
            evidence_json = json.dumps(evidence, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Lesson evidence must contain only finite JSON values.") from exc

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
        # Rank across the full validated corpus rather than only the 100 newest
        # records, so older useful lessons remain discoverable as memory grows.
        return search_validated_lessons(incoming_keywords, limit=limit)

    @staticmethod
    def get_recent_task_history(limit: int = 20) -> List[Dict[str, Any]]:
        from .storage import list_tasks
        return list_tasks(limit)
