import os
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .storage import save_task, update_task, get_task
from .storage import save_lesson
from .config import USE_PAID_AI
from .storage import get_connection
from .storage import list_lessons, list_tasks
from .storage import save_evaluation
from .evaluator import Evaluator
from .executor import safe_execute_local


class LocalTaskExecutor:
    def __init__(self, provider: Optional[str] = None):
        self.provider = provider or "local"
        self.enabled = not (provider and provider != "local" and not USE_PAID_AI)

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if self.provider == "local":
            return safe_execute_local(task)
        if self.provider in {"openai"}:
            if not USE_PAID_AI:
                raise RuntimeError("Paid AI providers are disabled unless explicitly configured.")
            raise RuntimeError("External AI providers are not enabled in this build.")
        raise ValueError(f"Unsupported provider: {self.provider}")
