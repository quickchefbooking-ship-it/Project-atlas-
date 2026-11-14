"""Durable, fenced step claims for Professor plans.

This repository coordinates step ownership only. It does not invoke capability
handlers, create retries, or authorize external side effects. Expired claims are
moved to recovery_required and are never automatically replayed.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .plan_contract import PlanState


class StepExecutionError(RuntimeError):
    """Base error for persisted step coordination."""


class StepPlanNotRunning(StepExecutionError):
    """A plan must be running before a worker can claim a step."""


class StepNotFound(StepExecutionError):
    """The requested plan step does not exist."""


class StepLeaseConflict(StepExecutionError):
    """The supplied worker lease is stale, expired or no longer owned."""


@dataclass(frozen=True)
class StepLease:
    plan_id: str
    step_id: str
    worker_id: str
    attempt_number: int
    fencing_token: int
    lease_expires_at: float


@dataclass(frozen=True)
class StepExecutionRecord:
    plan_id: str
    step_id: str
    ordinal: int
    capability: str
    capability_version: str | None
    risk: str
    state: str
    attempt_number: int
    fencing_token: int
    worker_id: str | None
    lease_expires_at: float | None
    result: Any
    error_code: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class StepExecutionEvent:
    plan_id: str
    step_id: str
    event_type: str
    attempt_number: int
    worker_id: str | None
    fencing_token: int
    details: dict[str, Any]
    created_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_step_execution_schema(connection: sqlite3.Connection) -> None:
    """Create additive step tables; safe to call for an existing prototype DB."""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS professor_plan_steps (
            plan_id TEXT NOT NULL REFERENCES professor_plans(plan_id) ON DELETE RESTRICT,
            step_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
            capability TEXT NOT NULL,
            capability_version TEXT,
            risk TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN
                ('pending','claimed','succeeded','failed','cancelled','recovery_required')),
            attempt_number INTEGER NOT NULL DEFAULT 0 CHECK(attempt_number >= 0),
            worker_id TEXT,
            fencing_token INTEGER NOT NULL DEFAULT 0 CHECK(fencing_token >= 0),
            lease_expires_at REAL,
            result_json TEXT,
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(plan_id, step_id),
            UNIQUE(plan_id, ordinal),
            CHECK(
                (state = 'claimed' AND worker_id IS NOT NULL AND lease_expires_at IS NOT NULL)
                OR
                (state <> 'claimed' AND lease_expires_at IS NULL)
            )
        );

        CREATE INDEX IF NOT EXISTS idx_professor_plan_steps_ready
            ON professor_plan_steps(plan_id, state, ordinal);

        CREATE TABLE IF NOT EXISTS professor_plan_step_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK(event_type IN
                ('claimed','heartbeat','succeeded','failed','lease_expired')),
            attempt_number INTEGER NOT NULL,
            worker_id TEXT,
            fencing_token INTEGER NOT NULL,
            details_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(plan_id, step_id)
                REFERENCES professor_plan_steps(plan_id, step_id) ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_professor_plan_step_events
            ON professor_plan_step_events(plan_id, step_id, event_id);
        """
    )


def _json_payload(value: Any, *, max_bytes: int = 65_536) -> str:
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Step result must be finite JSON data.") from exc
    if len(encoded.encode("utf-8")) > max_bytes:
        raise ValueError("Step result exceeds the 64 KiB limit.")
    return encoded


class StepExecutionRepository:
    """Atomic, single-owner step claims with monotonically increasing fencing."""

    def __init__(self, connection_factory) -> None:
        if not callable(connection_factory):
            raise TypeError("connection_factory must be callable.")
        self._connection_factory = connection_factory
        conn = self._connection_factory()
        try:
            initialize_step_execution_schema(conn)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _validate_worker(worker_id: str, lease_seconds: int) -> None:
        if not isinstance(worker_id, str) or not worker_id.strip() or len(worker_id) > 128:
            raise ValueError("worker_id must be a non-empty string of at most 128 characters.")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 1 <= lease_seconds <= 900:
            raise ValueError("lease_seconds must be between 1 and 900.")

    @staticmethod
    def _event(conn, plan_id, step_id, event_type, attempt, worker, token, details=None):
        conn.execute(
            """INSERT INTO professor_plan_step_events
               (plan_id, step_id, event_type, attempt_number, worker_id,
                fencing_token, details_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (plan_id, step_id, event_type, attempt, worker, token,
             _json_payload(details or {}), _now_iso()),
        )

    def _expire_claims(self, conn, plan_id: str, now: float) -> int:
        rows = conn.execute(
            """SELECT step_id, attempt_number, worker_id, fencing_token
               FROM professor_plan_steps
               WHERE plan_id = ? AND state = 'claimed' AND lease_expires_at <= ?
               ORDER BY ordinal""",
            (plan_id, now),
        ).fetchall()
        for row in rows:
            cursor = conn.execute(
                """UPDATE professor_plan_steps
                   SET state = 'recovery_required', worker_id = NULL,
                       lease_expires_at = NULL, updated_at = ?
                   WHERE plan_id = ? AND step_id = ? AND state = 'claimed'
                     AND fencing_token = ? AND lease_expires_at <= ?""",
                (_now_iso(), plan_id, row["step_id"], row["fencing_token"], now),
            )
            if cursor.rowcount == 1:
                self._event(
                    conn, plan_id, row["step_id"], "lease_expired",
                    row["attempt_number"], row["worker_id"], row["fencing_token"],
                    {"decision": "recovery_required", "automatic_replay": False},
                )
        return len(rows)

    def claim_next_step(self, plan_id: str, worker_id: str, lease_seconds: int = 60) -> StepLease | None:
        self._validate_worker(worker_id, lease_seconds)
        if not isinstance(plan_id, str) or not plan_id.strip() or len(plan_id) > 128:
            raise ValueError("plan_id must be a non-empty string of at most 128 characters.")
        conn = self._connection_factory()
        now = time.time()
        try:
            conn.execute("BEGIN IMMEDIATE")
            plan = conn.execute(
                "SELECT state, plan_json FROM professor_plans WHERE plan_id = ?", (plan_id,)
            ).fetchone()
            if plan is None:
                raise StepNotFound("Plan was not found.")
            if plan["state"] != PlanState.RUNNING.value:
                raise StepPlanNotRunning("Plan must be running before steps can be claimed.")
            self._expire_claims(conn, plan_id, now)
            plan_steps = {
                item["step_id"]: tuple(item.get("depends_on", ()))
                for item in json.loads(plan["plan_json"])["steps"]
            }
            pending_rows = conn.execute(
                """SELECT step_id, attempt_number, fencing_token, risk
                   FROM professor_plan_steps
                   WHERE plan_id = ? AND state = 'pending'
                   ORDER BY ordinal""",
                (plan_id,),
            ).fetchall()
            row = next(
                (
                    candidate for candidate in pending_rows
                    if all(
                        conn.execute(
                            """SELECT state FROM professor_plan_steps
                               WHERE plan_id = ? AND step_id = ?""",
                            (plan_id, dependency),
                        ).fetchone()["state"] == "succeeded"
                        for dependency in plan_steps[candidate["step_id"]]
                    )
                ),
                None,
            )
            if row is None:
                conn.commit()
                return None
            if row["risk"] in {"external_side_effect", "privileged"}:
                raise StepExecutionError(
                    "External and privileged steps remain blocked until verified, "
                    "action-bound authorisation is implemented."
                )
            attempt = row["attempt_number"] + 1
            token = row["fencing_token"] + 1
            expires = now + lease_seconds
            updated = _now_iso()
            cursor = conn.execute(
                """UPDATE professor_plan_steps
                   SET state = 'claimed', attempt_number = ?, worker_id = ?,
                       fencing_token = ?, lease_expires_at = ?, updated_at = ?
                   WHERE plan_id = ? AND step_id = ? AND state = 'pending'""",
                (attempt, worker_id, token, expires, updated, plan_id, row["step_id"]),
            )
            if cursor.rowcount != 1:
                raise StepLeaseConflict("Step was claimed concurrently.")
            self._event(conn, plan_id, row["step_id"], "claimed", attempt, worker_id, token,
                        {"lease_seconds": lease_seconds})
            conn.commit()
            return StepLease(plan_id, row["step_id"], worker_id, attempt, token, expires)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def heartbeat(self, lease: StepLease, lease_seconds: int = 60) -> StepLease:
        if not isinstance(lease, StepLease):
            raise TypeError("A StepLease is required.")
        self._validate_worker(lease.worker_id, lease_seconds)
        now = time.time()
        expires = now + lease_seconds
        conn = self._connection_factory()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """UPDATE professor_plan_steps
                   SET lease_expires_at = ?, updated_at = ?
                   WHERE plan_id = ? AND step_id = ? AND state = 'claimed'
                     AND worker_id = ? AND attempt_number = ? AND fencing_token = ?
                     AND lease_expires_at > ?""",
                (expires, _now_iso(), lease.plan_id, lease.step_id, lease.worker_id,
                 lease.attempt_number, lease.fencing_token, now),
            )
            if cursor.rowcount != 1:
                raise StepLeaseConflict("Step lease is stale, expired or no longer owned.")
            self._event(conn, lease.plan_id, lease.step_id, "heartbeat",
                        lease.attempt_number, lease.worker_id, lease.fencing_token,
                        {"lease_seconds": lease_seconds})
            conn.commit()
            return StepLease(
                lease.plan_id, lease.step_id, lease.worker_id,
                lease.attempt_number, lease.fencing_token, expires,
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def complete(self, lease: StepLease, *, result: Any = None, error_code: str | None = None) -> StepExecutionRecord:
        if not isinstance(lease, StepLease):
            raise TypeError("A StepLease is required.")
        if error_code is not None and (
            not isinstance(error_code, str) or not error_code.strip() or len(error_code) > 128
        ):
            raise ValueError("error_code must be a non-empty string of at most 128 characters.")
        if error_code is not None and result is not None:
            raise ValueError("Provide either a result or an error_code, not both.")
        result_json = _json_payload(result) if error_code is None else None
        target = "failed" if error_code is not None else "succeeded"
        now = time.time()
        conn = self._connection_factory()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """UPDATE professor_plan_steps
                   SET state = ?, worker_id = NULL, lease_expires_at = NULL,
                       result_json = ?, error_code = ?, updated_at = ?
                   WHERE plan_id = ? AND step_id = ? AND state = 'claimed'
                     AND worker_id = ? AND attempt_number = ? AND fencing_token = ?
                     AND lease_expires_at > ?""",
                (target, result_json, error_code, _now_iso(), lease.plan_id,
                 lease.step_id, lease.worker_id, lease.attempt_number,
                 lease.fencing_token, now),
            )
            if cursor.rowcount != 1:
                raise StepLeaseConflict("Step lease is stale, expired or no longer owned.")
            self._event(conn, lease.plan_id, lease.step_id, target,
                        lease.attempt_number, lease.worker_id, lease.fencing_token,
                        {"error_code": error_code} if error_code else {"result_recorded": result is not None})
            row = conn.execute(
                """SELECT * FROM professor_plan_steps
                   WHERE plan_id = ? AND step_id = ?""",
                (lease.plan_id, lease.step_id),
            ).fetchone()
            conn.commit()
            return self._record(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_step(self, plan_id: str, step_id: str) -> StepExecutionRecord:
        conn = self._connection_factory()
        try:
            row = conn.execute(
                "SELECT * FROM professor_plan_steps WHERE plan_id = ? AND step_id = ?",
                (plan_id, step_id),
            ).fetchone()
            if row is None:
                raise StepNotFound("Plan step was not found.")
            return self._record(row)
        finally:
            conn.close()

    def list_steps(self, plan_id: str) -> tuple[StepExecutionRecord, ...]:
        conn = self._connection_factory()
        try:
            rows = conn.execute(
                "SELECT * FROM professor_plan_steps WHERE plan_id = ? ORDER BY ordinal",
                (plan_id,),
            ).fetchall()
            return tuple(self._record(row) for row in rows)
        finally:
            conn.close()

    def list_events(self, plan_id: str, step_id: str) -> tuple[StepExecutionEvent, ...]:
        conn = self._connection_factory()
        try:
            rows = conn.execute(
                """SELECT * FROM professor_plan_step_events
                   WHERE plan_id = ? AND step_id = ? ORDER BY event_id""",
                (plan_id, step_id),
            ).fetchall()
            return tuple(
                StepExecutionEvent(
                    row["plan_id"], row["step_id"], row["event_type"],
                    row["attempt_number"], row["worker_id"], row["fencing_token"],
                    json.loads(row["details_json"]), row["created_at"],
                )
                for row in rows
            )
        finally:
            conn.close()

    @staticmethod
    def _record(row) -> StepExecutionRecord:
        return StepExecutionRecord(
            plan_id=row["plan_id"], step_id=row["step_id"], ordinal=row["ordinal"],
            capability=row["capability"], capability_version=row["capability_version"],
            risk=row["risk"], state=row["state"], attempt_number=row["attempt_number"],
            fencing_token=row["fencing_token"], worker_id=row["worker_id"],
            lease_expires_at=row["lease_expires_at"],
            result=json.loads(row["result_json"]) if row["result_json"] is not None else None,
            error_code=row["error_code"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
