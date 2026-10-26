import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from .storage import list_lessons, save_lesson, get_evaluations_for_task


class LearningMemory:
    def __init__(self):
        pass

    @staticmethod
    def _keywords(text: str) -> set[str]:
        return {word.lower() for word in re.findall(r"[a-zA-Z0-9_]+", text) if len(word) > 2}

    @staticmethod
    def save_lesson_for_task(task_id: str, lesson_type: str, summary: str, source: str, evidence: Dict[str, Any], validated: bool = False) -> Dict[str, Any]:
        payload = {
            "id": f"lesson-{task_id}-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            "task_id": task_id,
            "lesson_type": lesson_type,
            "summary": summary,
            "source": source,
            "evidence_json": json.dumps(evidence, sort_keys=True),
            "validated": validated,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        save_lesson(payload)
        return payload

    @staticmethod
    def get_relevant_lessons(task_description: str, limit: int = 5) -> List[Dict[str, Any]]:
        incoming_keywords = LearningMemory._keywords(task_description)
        lesson_rows = list_lessons(limit=100)
        scored: list[tuple[float, Dict[str, Any]]] = []
        for row in lesson_rows:
            if row.get("validated") not in (1, True):
                continue
            lesson_text = f"{row.get('summary', '')} {row.get('source', '')}"
            lesson_keywords = LearningMemory._keywords(lesson_text)
            overlap = len(incoming_keywords & lesson_keywords)
            if overlap:
                scored.append((float(overlap), row))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [row for _, row in scored[:limit]]

    @staticmethod
    def get_recent_task_history(limit: int = 20) -> List[Dict[str, Any]]:
        from .storage import list_tasks
        return list_tasks(limit)

