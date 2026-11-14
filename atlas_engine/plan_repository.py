"""SQLite persistence for Professor plans.

This repository persists plans and provides compare-and-swap state changes.
It deliberately does not execute steps, resolve capabilities, or authorize
external actions. Use the application's existing database path and connection
factory so plans share the prototype's configured SQLite database.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .plan_contract import PlanState, PlanStep, ProfessorPlan, RiskClass
from .storage import get_connection


class PlanRepositoryError(RuntimeError):
    """Base error for Professor plan persistence."""


class PlanAlreadyExists(PlanRepositoryError):
    """A plan identifier is already present."""


class PlanNotFound(PlanRepositoryError):
    """The requested plan does not exist."""


class PlanStateConflict(PlanRepositoryError):
    """A plan changed state before this transition could be applied."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encode_plan(plan: ProfessorPlan) -> str:
    payload: dict[str, Any] = {
        "plan_id": plan.plan_id,
        "objective": plan.objective,
        "acceptance_criteria": list(plan.acceptance_criteria),
        "state": plan.state.value,
        "steps": [
            {
                "step_id": step.step_id,
                "capability": step.capability,
                "objective": step.objective,
                "risk": step.risk.value,
                "depends_on": list(step.depends_on),
                "required_scopes": list(step.required_scopes),
                "expected_output": step.expected_output,
                "timeout_seconds": step.timeout_seconds,
                "resource_budget": step.resource_budget,
            }
            for step in plan.steps
        ],
    }
    return json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True)


def _decode_plan(raw: str) -> ProfessorPlan:
    payload = json.loads(raw)
    steps = tuple(
        PlanStep(
            step_id=item["step_id"],
            capability=item["capability"],
            objective=item["objective"],
            risk=RiskClass(item["risk"]),
            depends_on=tuple(item["depends_on"]),
            required_scopes=tuple(item["required_scopes"]),
            expected_output=item["expected_output"],
            timeout_seconds=item["timeout_seconds"],
            resource_budget=item["resource_budget"],
        )
        for item in payload["steps"]
    )
    return ProfessorPlan(
        plan_id=payload["plan_id"],
        objective=payload["objective"],
        acceptance_criteria=tuple(payload["acceptance_criteria"]),
        steps=steps,
        state=PlanState(payload["state"]),
    )


class PlanRepository:
    """Durable plan storage with atomic state transitions, not a task runner."""

    def __init__(self, connection_factory=get_connection) -> None:
        self._connection_factory = connection_factory
        self._initialize()

    def _initialize(self) -> None:
        conn = self._connection_factory()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS professor_plans (
                    plan_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL CHECK(state IN (
                        'draft','ready','awaiting_approval','approved',
                        'running','succeeded','failed','cancelled'
                    )),
                    plan_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_professor_plans_state_updated
                ON professor_plans(state, updated_at DESC)
                """
            )
            conn.commit()
        finally:
            conn.close()

    def create(self, plan: ProfessorPlan) -> ProfessorPlan:
        if not isinstance(plan, ProfessorPlan):
            raise TypeError("A validated ProfessorPlan is required.")
        conn = self._connection_factory()
        now = _now()
        try:
            try:
                conn.execute(
                    """
                    INSERT INTO professor_plans(plan_id, state, plan_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (plan.plan_id, plan.state.value, _encode_plan(plan), now, now),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise PlanAlreadyExists(f"Plan {plan.plan_id} already exists.") from exc
            return plan
        finally:
            conn.close()

    def get(self, plan_id: str) -> ProfessorPlan:
        conn = self._connection_factory()
        try:
            row = conn.execute(
                "SELECT plan_json FROM professor_plans WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
            if row is None:
                raise PlanNotFound(f"Plan {plan_id} was not found.")
            return _decode_plan(row["plan_json"])
        finally:
            conn.close()

    def list(self, *, state: PlanState | None = None, limit: int = 50) -> tuple[ProfessorPlan, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200.")
        conn = self._connection_factory()
        try:
            if state is None:
                rows = conn.execute(
                    "SELECT plan_json FROM professor_plans ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                if not isinstance(state, PlanState):
                    raise TypeError("state must be a PlanState.")
                rows = conn.execute(
                    "SELECT plan_json FROM professor_plans WHERE state = ? ORDER BY created_at DESC LIMIT ?",
                    (state.value, limit),
                ).fetchall()
            return tuple(_decode_plan(row["plan_json"]) for row in rows)
        finally:
            conn.close()

    def transition(
        self,
        plan_id: str,
        *,
        expected_state: PlanState,
        new_state: PlanState,
        approval_reference: str | None = None,
    ) -> ProfessorPlan:
        """Compare-and-swap one state; approval transitions require a reference."""
        if not isinstance(expected_state, PlanState) or not isinstance(new_state, PlanState):
            raise TypeError("expected_state and new_state must be PlanState values.")
        allowed = {
            PlanState.DRAFT: {PlanState.READY, PlanState.AWAITING_APPROVAL},
            PlanState.AWAITING_APPROVAL: {PlanState.APPROVED},
            PlanState.READY: {PlanState.RUNNING, PlanState.CANCELLED},
            PlanState.APPROVED: {PlanState.RUNNING, PlanState.CANCELLED},
            PlanState.RUNNING: {PlanState.SUCCEEDED, PlanState.FAILED, PlanState.CANCELLED},
        }
        if new_state not in allowed.get(expected_state, set()):
            raise PlanStateConflict(f"Transition {expected_state.value} -> {new_state.value} is not allowed.")
        if new_state is PlanState.APPROVED and (
            not isinstance(approval_reference, str)
            or not approval_reference.strip()
            or len(approval_reference) > 256
        ):
            raise PlanStateConflict("An action-bound approval reference is required.")
        conn = self._connection_factory()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT plan_json FROM professor_plans WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
            if row is None:
                conn.rollback()
                raise PlanNotFound(f"Plan {plan_id} was not found.")
            current = _decode_plan(row["plan_json"])
            if current.state is not expected_state:
                conn.rollback()
                raise PlanStateConflict(
                    f"Plan state is {current.state.value}, not {expected_state.value}."
                )
            updated = ProfessorPlan(
                plan_id=current.plan_id,
                objective=current.objective,
                acceptance_criteria=current.acceptance_criteria,
                steps=current.steps,
                state=new_state,
            )
            cursor = conn.execute(
                """
                UPDATE professor_plans
                SET state = ?, plan_json = ?, updated_at = ?
                WHERE plan_id = ? AND state = ?
                """,
                (new_state.value, _encode_plan(updated), _now(), plan_id, expected_state.value),
            )
            if cursor.rowcount != 1:
                conn.rollback()
                raise PlanStateConflict("Plan state changed concurrently.")
            conn.commit()
            return updated
        finally:
            conn.close()
