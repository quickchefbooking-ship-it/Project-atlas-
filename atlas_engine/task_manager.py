import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError

from .retry_policy import RetryPolicy

logger = logging.getLogger(__name__)

MAX_TASK_TITLE_CHARS = 200
MAX_TASK_DESCRIPTION_CHARS = 10_000
MAX_TASK_CRITERIA_ITEMS = 100
MAX_TASK_CRITERIA_BYTES = 16_384


def _validate_task_text(value: str, field_name: str, max_chars: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Task {field_name} must not be blank.")
    if len(value) > max_chars:
        raise ValueError(f"Task {field_name} must not exceed {max_chars} characters.")
    return value


def _serialize_task_criteria(value: Any) -> str:
    if not isinstance(value, (list, dict)):
        raise ValueError("Task success criteria must be a JSON object or array.")
    if isinstance(value, list) and len(value) > MAX_TASK_CRITERIA_ITEMS:
        raise ValueError(f"Task success criteria must not contain more than {MAX_TASK_CRITERIA_ITEMS} items.")
    nested_criteria = value.get("criteria") if isinstance(value, dict) else None
    if isinstance(nested_criteria, list) and len(nested_criteria) > MAX_TASK_CRITERIA_ITEMS:
        raise ValueError(f"Task success criteria must not contain more than {MAX_TASK_CRITERIA_ITEMS} items.")
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("Task success criteria must be finite, valid JSON within the supported structure.") from exc
    if len(encoded.encode("utf-8")) > MAX_TASK_CRITERIA_BYTES:
        raise ValueError(f"Task success criteria must not exceed {MAX_TASK_CRITERIA_BYTES} UTF-8 bytes.")
    return encoded


class TaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TASK_TITLE_CHARS)
    description: str = Field(min_length=1, max_length=MAX_TASK_DESCRIPTION_CHARS)
    success_criteria: list[dict[str, Any]] | list[str] | dict[str, Any] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        try:
            return _validate_task_text(value, "title", MAX_TASK_TITLE_CHARS)
        except ValueError as exc:
            raise PydanticCustomError("task_title_invalid", str(exc)) from exc

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        try:
            return _validate_task_text(value, "description", MAX_TASK_DESCRIPTION_CHARS)
        except ValueError as exc:
            raise PydanticCustomError("task_description_invalid", str(exc)) from exc

    @field_validator("success_criteria")
    @classmethod
    def validate_success_criteria(cls, value: Any) -> Any:
        try:
            _serialize_task_criteria(value)
        except ValueError as exc:
            # PydanticCustomError keeps the original exception object out of
            # FastAPI's JSON validation response context.
            raise PydanticCustomError("task_criteria_invalid", str(exc)) from exc
        return value

class ProposalReviewInput(BaseModel):
    action: str
    approved_by: str

class Task(BaseModel):
    id: str
    title: str
    description: str
    success_criteria: Any = Field(default_factory=list)
    status: str = "pending"
    attempts: int = 0
    score: float = 0.0
    result: dict[str, Any] | None = None
    created_at: str
    updated_at: str

class TaskManager:
    def __init__(self, storage_backend: Any):
        self.storage_backend = storage_backend

    def create_task(self, title: str, description: str, success_criteria: Any) -> Task:
        title = _validate_task_text(title, "title", MAX_TASK_TITLE_CHARS)
        description = _validate_task_text(description, "description", MAX_TASK_DESCRIPTION_CHARS)
        criteria = success_criteria if success_criteria is not None else []
        criteria_json = _serialize_task_criteria(criteria)
        now = self.storage_backend.now_isoformat()
        task_id = f"task-{os.urandom(12).hex()}"
        row = {
            "id": task_id, "title": title, "description": description,
            "success_criteria_json": criteria_json, "status": "pending",
            "attempts": 0, "score": 0.0, "result_json": None,
            "created_at": now, "updated_at": now,
        }
        self.storage_backend.save_task(row)
        return Task(id=task_id, title=title, description=description,
                    success_criteria=criteria, created_at=now, updated_at=now)

    def get_task(self, task_id: str) -> Task | None:
        row = self.storage_backend.get_task(task_id)
        if row is None:
            return None
        return Task(
            id=row["id"], title=row["title"], description=row["description"],
            success_criteria=json.loads(row["success_criteria_json"]),
            status=row["status"], attempts=row["attempts"], score=row["score"],
            result=json.loads(row["result_json"]) if row.get("result_json") else None,
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def list_tasks(self, limit: int = 20) -> list[Task]:
        rows = self.storage_backend.list_tasks(limit)
        return [self.get_task(row["id"]) for row in rows]

    def claim_task(self, task_id: str) -> bool:
        """Legacy atomic claim retained for callers that do not use lease tracking."""
        return self.storage_backend.claim_task(task_id)

    def claim_task_with_lease(self, task_id: str, worker_id: str,
                              lease_seconds: int = 60) -> dict[str, Any] | None:
        return self.storage_backend.claim_task_with_lease(task_id, worker_id, lease_seconds)

    def heartbeat_task_attempt(self, task_id: str, attempt: dict[str, Any],
                               lease_seconds: int = 60) -> bool:
        return self.storage_backend.heartbeat_task_attempt(
            task_id, attempt["attempt_id"], attempt["worker_id"],
            attempt["fencing_token"], lease_seconds,
        )

    def complete_with_evaluation(self, task_id: str, record: dict[str, Any],
                                 status: str, result: dict[str, Any],
                                 attempt: dict[str, Any] | None = None) -> bool:
        """Persist task, evaluation and lease completion in one transaction."""
        return self.storage_backend.complete_task_with_evaluation(
            task_id, record, status, result, attempt=attempt
        )

    def get_task_cancellation(self, task_id: str, attempt_id: str | None = None):
        return self.storage_backend.get_task_cancellation(task_id, attempt_id)

    def acknowledge_task_cancellation(self, task_id: str, attempt: dict[str, Any],
                                      record: dict[str, Any]) -> bool:
        return self.storage_backend.acknowledge_task_cancellation(task_id, attempt, record)

    def update_status(self, task_id: str, status: str, score: float | None = None,
                      result: dict[str, Any] | None = None,
                      increment_attempt: bool = False) -> Task | None:
        task = self.get_task(task_id)
        if task is None:
            return None
        updates: dict[str, Any] = {"status": status, "updated_at": self.storage_backend.now_isoformat()}
        if score is not None:
            updates["score"] = score
        if result is not None:
            updates["result_json"] = json.dumps(result, sort_keys=True)
        if increment_attempt:
            updates["attempts"] = task.attempts + 1
        self.storage_backend.update_task(task_id, updates)
        return self.get_task(task_id)

class TaskAPI:
    def __init__(self, manager, executor, evaluator, memory, improvement, tester):
        self.manager, self.executor, self.evaluator = manager, executor, evaluator
        self.memory, self.improvement, self.tester = memory, improvement, tester

    def health(self):
        return {"status": "ok", "service": "AtlasOnePro Professor Core"}

    def create_task(self, payload: TaskInput):
        return self.manager.create_task(payload.title, payload.description, payload.success_criteria).model_dump()

    def list_tasks(self):
        return [task.model_dump() for task in self.manager.list_tasks()]

    def _finish_cancelled(self, task_id: str, lease: dict[str, Any], cancellation: dict[str, Any]):
        record = {
            "id": f"evaluation-{os.urandom(12).hex()}",
            "task_id": task_id,
            "method": "cancelled",
        }
        if self.manager.acknowledge_task_cancellation(task_id, lease, record):
            return {
                "task_id": task_id,
                "status": "cancelled",
                "cancellation_id": cancellation["cancellation_id"],
                "message": "Cancellation acknowledged at a safe point.",
            }
        return {
            "task_id": task_id,
            "status": "outcome_unconfirmed",
            "error": "Cancellation could not be confirmed by the current lease owner. Recovery is required.",
        }

    def run_task(self, task_id: str):
        task = self.manager.get_task(task_id)
        if task is None:
            return {"error": "Task not found"}
        worker_id = f"worker-{os.urandom(12).hex()}"
        lease = self.manager.claim_task_with_lease(task_id, worker_id, lease_seconds=60)
        if lease is None:
            current = self.manager.get_task(task_id)
            return {
                "task_id": task_id,
                "status": current.status if current is not None else "unavailable",
                "error": "Task is already running, awaiting recovery, or is not pending.",
            }
        # Reload after the atomic claim so the executor sees the persisted attempt count.
        task = self.manager.get_task(task_id)
        if task is None:
            return {"task_id": task_id, "status": "unavailable", "error": "Task is unavailable."}
        heartbeat_stop = threading.Event()
        heartbeat_lost = threading.Event()

        def maintain_lease():
            while not heartbeat_stop.wait(20):
                try:
                    if not self.manager.heartbeat_task_attempt(task_id, lease, lease_seconds=60):
                        heartbeat_lost.set()
                        return
                except Exception as heartbeat_error:
                    logger.warning(
                        "Task lease heartbeat failed for task_id=%s error_type=%s",
                        task_id, type(heartbeat_error).__name__,
                    )
                    heartbeat_lost.set()
                    return

        heartbeat_thread = threading.Thread(
            target=maintain_lease, name=f"atlas-lease-{lease['attempt_id']}", daemon=True
        )
        heartbeat_thread.start()
        phase = "execution"
        try:
            cancellation = self.manager.get_task_cancellation(task_id, lease["attempt_id"])
            if cancellation is not None and cancellation["state"] == "requested":
                return self._finish_cancelled(task_id, lease, cancellation)

            # Retrieve only validated lessons; pass them as context to capable executors.
            # The restricted local arithmetic executor deliberately ignores this context.
            relevant_lessons = self.memory.get_relevant_lessons(task.description) if hasattr(
                self.memory, "get_relevant_lessons"
            ) else []
            try:
                from .source_division import retrieve as retrieve_sources
                source_documents = retrieve_sources(task.description)
            except Exception as source_error:
                logger.warning(
                    "Source Division retrieval unavailable for task_id=%s error_type=%s",
                    task_id,
                    type(source_error).__name__,
                )
                source_documents = []
            cancellation = self.manager.get_task_cancellation(task_id, lease["attempt_id"])
            if cancellation is not None and cancellation["state"] == "requested":
                return self._finish_cancelled(task_id, lease, cancellation)
            # The local executor is deterministic and bounded. Cancellation is
            # cooperative: a request received during this synchronous call is
            # acknowledged immediately after it returns, before evaluation/commit.
            execution_deadline = time.monotonic() + RetryPolicy().per_attempt_timeout_seconds
            result = self.executor.execute({
                "title": task.title,
                "description": task.description,
                "relevant_lessons": relevant_lessons,
                "source_documents": source_documents,
                "_execution_deadline_monotonic": execution_deadline,
            })
            cancellation = self.manager.get_task_cancellation(task_id, lease["attempt_id"])
            if cancellation is not None and cancellation["state"] == "requested":
                return self._finish_cancelled(task_id, lease, cancellation)
            evaluation = self.evaluator.evaluate(result, task.success_criteria)
            status = "passed" if evaluation["passed"] else "failed"

            # Commit the terminal task state and its evaluation together. A partial
            # write must never leave a terminal task without its audit record.
            evaluation_record = {
                "id": f"evaluation-{os.urandom(12).hex()}",
                "task_id": task_id,
                "passed": evaluation["passed"],
                "score": evaluation["score"],
                "reasons_json": json.dumps(evaluation["reasons"], sort_keys=True),
                "missing_requirements_json": json.dumps(evaluation["missing_requirements"], sort_keys=True),
                "method": evaluation["method"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            phase = "persistence"
            if not self.manager.complete_with_evaluation(task_id, evaluation_record, status, result, attempt=lease):
                cancellation = self.manager.get_task_cancellation(task_id, lease["attempt_id"])
                if cancellation is not None and cancellation["state"] == "requested":
                    return self._finish_cancelled(task_id, lease, cancellation)
                current = self.manager.get_task(task_id)
                logger.error(
                    "Task completion was not committed for task_id=%s current_status=%s",
                    task_id,
                    current.status if current is not None else "unavailable",
                )
                return {
                    "task_id": task_id,
                    "status": "outcome_unconfirmed",
                    "error": "Task completion was not committed. Its final state requires recovery.",
                }

            if not evaluation["passed"]:
                try:
                    self.memory.save_lesson_for_task(
                        task_id,
                        "failure",
                        "Task failed its success criteria.",
                        "deterministic-evaluation",
                        {"evaluation": evaluation},
                        validated=False,
                    )
                except Exception as lesson_error:
                    # Learning-record failure must not rewrite an already committed
                    # task outcome or hide its persisted evaluation from the caller.
                    logger.warning(
                        "Failure lesson persistence unavailable for task_id=%s error_type=%s",
                        task_id,
                        type(lesson_error).__name__,
                    )
            return {"task_id": task_id, "status": status, "result": result, "evaluation": evaluation}
        except Exception as exc:
            error_type = type(exc).__name__
            try:
                cancellation = self.manager.get_task_cancellation(task_id, lease["attempt_id"])
                if cancellation is not None and cancellation["state"] == "requested":
                    return self._finish_cancelled(task_id, lease, cancellation)
            except Exception as cancellation_error:
                logger.warning(
                    "Cancellation check failed for task_id=%s error_type=%s",
                    task_id, type(cancellation_error).__name__,
                )
            if phase == "persistence":
                # The completion transaction rolls back on failure. Do not write a
                # separate terminal status without its evaluation: that would create
                # an incomplete audit trail and falsely imply durable completion.
                logger.error(
                    "Task outcome persistence failed for task_id=%s error_type=%s",
                    task_id,
                    error_type,
                )
                return {
                    "task_id": task_id,
                    "status": "outcome_unconfirmed",
                    "error": "Task outcome could not be persisted. Its final state requires recovery.",
                }

            # Execution exceptions are failed outcomes too. Persist a sanitised,
            # zero-score evaluation with the terminal task state when storage allows.
            failure_record = {
                "id": f"evaluation-{os.urandom(12).hex()}",
                "task_id": task_id,
                "passed": False,
                "score": 0.0,
                "reasons_json": json.dumps(["Task execution failed.", f"error_type={error_type}"]),
                "missing_requirements_json": json.dumps(["Task execution completed successfully."]),
                "method": "execution_error",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                committed = self.manager.complete_with_evaluation(
                    task_id, failure_record, "failed", {"error_type": error_type}, attempt=lease
                )
                if not committed:
                    current = self.manager.get_task(task_id)
                    logger.error(
                        "Task failure outcome was not committed for task_id=%s current_status=%s",
                        task_id,
                        current.status if current is not None else "unavailable",
                    )
                    return {
                        "task_id": task_id,
                        "status": "outcome_unconfirmed",
                        "error": "Task failure could not be persisted with its evaluation. Its final state requires recovery.",
                    }
            except Exception as persistence_error:
                logger.error(
                    "Task failure outcome persistence failed for task_id=%s error_type=%s",
                    task_id,
                    type(persistence_error).__name__,
                )
                return {
                    "task_id": task_id,
                    "status": "outcome_unconfirmed",
                    "error": "Task failure could not be persisted with its evaluation. Its final state requires recovery.",
                }

            # Keep exception messages out of API responses and logs: they can contain
            # credentials, file paths or private task data. Record only the error type.
            if callable(getattr(self.memory, "save_lesson_for_task", None)):
                try:
                    self.memory.save_lesson_for_task(
                        task_id,
                        "execution_failure",
                        "Task execution failed; review the sanitised diagnostic type before reusing this pattern.",
                        "execution-error",
                        {
                            "error_type": error_type,
                            "evaluation_id": failure_record["id"],
                        },
                        validated=False,
                    )
                except Exception as lesson_error:
                    # Learning is best-effort and must not alter the committed failure outcome.
                    logger.warning(
                        "Execution failure lesson persistence unavailable for task_id=%s error_type=%s",
                        task_id,
                        type(lesson_error).__name__,
                    )
            logger.error(
                "Task execution failed for task_id=%s error_type=%s",
                task_id,
                error_type,
            )
            return {
                "task_id": task_id,
                "status": "failed",
                "error": "Task execution failed. Check the server diagnostics using the task ID.",
            }
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1)

    def get_evaluations(self, task_id: str):
        from .storage import get_evaluations_for_task
        return get_evaluations_for_task(task_id)

    def list_lessons(self):
        from .storage import list_lessons
        return list_lessons()

    def list_proposals(self):
        return self.improvement.list_proposals()

    def review_proposal(self, proposal_id: str, payload: ProposalReviewInput):
        return self.improvement.review_proposal(proposal_id, payload.action, payload.approved_by)

    def dashboard(self):
        return {"tasks": self.list_tasks(), "lessons": self.list_lessons(),
                "proposals": self.list_proposals()}
