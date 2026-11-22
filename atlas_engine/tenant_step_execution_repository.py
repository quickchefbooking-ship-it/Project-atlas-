"""Tenant-scoped, fenced Professor step ownership prototype.

This repository records ownership and outcomes only. It never invokes capability
handlers, retries expired work, or authorises external/privileged side effects.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .identity_policy import RequestPrincipal, authorize_tenant_resource


class TenantStepError(RuntimeError):
    """Base error for tenant-scoped step coordination."""


class TenantStepNotFound(TenantStepError):
    """A tenant-owned plan step does not exist."""


class TenantStepConflict(TenantStepError):
    """A step lease is stale, expired, or no longer owned."""


class TenantStepPlanNotRunning(TenantStepError):
    """A tenant plan must be running before a step can be claimed."""


@dataclass(frozen=True)
class TenantStepLease:
    tenant_id: str
    plan_id: str
    step_id: str
    worker_id: str
    attempt_number: int
    fencing_token: int
    lease_expires_at: float


@dataclass(frozen=True)
class TenantStepRecord:
    tenant_id: str
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


@dataclass(frozen=True)
class TenantStepEvent:
    tenant_id: str
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


def _json_payload(value: Any, max_bytes: int = 65_536) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False,
                             sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Step result must be finite JSON data.") from exc
    if len(encoded.encode("utf-8")) > max_bytes:
        raise ValueError("Step result exceeds the 64 KiB limit.")
    return encoded


def initialize_tenant_step_schema(db: sqlite3.Connection) -> None:
    """Create isolated run/event tables; tenant plan metadata must exist first."""
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS tenant_professor_step_runs (
      tenant_id TEXT NOT NULL, plan_id TEXT NOT NULL, step_id TEXT NOT NULL,
      state TEXT NOT NULL CHECK(state IN
        ('pending','claimed','succeeded','failed','cancelled','recovery_required')),
      attempt_number INTEGER NOT NULL DEFAULT 0 CHECK(attempt_number>=0),
      worker_id TEXT, fencing_token INTEGER NOT NULL DEFAULT 0 CHECK(fencing_token>=0),
      lease_expires_at REAL, result_json TEXT, error_code TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(tenant_id,plan_id,step_id),
      CHECK((state='claimed' AND worker_id IS NOT NULL AND lease_expires_at IS NOT NULL)
         OR (state<>'claimed' AND lease_expires_at IS NULL)),
      FOREIGN KEY(tenant_id,plan_id,step_id)
        REFERENCES tenant_professor_plan_steps(tenant_id,plan_id,step_id) ON DELETE RESTRICT
    );
    CREATE INDEX IF NOT EXISTS idx_tenant_step_runs_ready
      ON tenant_professor_step_runs(tenant_id,plan_id,state);
    CREATE TABLE IF NOT EXISTS tenant_professor_step_events (
      event_id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL,
      plan_id TEXT NOT NULL, step_id TEXT NOT NULL,
      event_type TEXT NOT NULL CHECK(event_type IN
        ('claimed','heartbeat','succeeded','failed','lease_expired')),
      attempt_number INTEGER NOT NULL, worker_id TEXT, fencing_token INTEGER NOT NULL,
      details_json TEXT NOT NULL, created_at TEXT NOT NULL,
      FOREIGN KEY(tenant_id,plan_id,step_id)
        REFERENCES tenant_professor_step_runs(tenant_id,plan_id,step_id) ON DELETE RESTRICT
    );
    CREATE INDEX IF NOT EXISTS idx_tenant_step_events
      ON tenant_professor_step_events(tenant_id,plan_id,step_id,event_id);
    CREATE TRIGGER IF NOT EXISTS tenant_step_events_no_update
      BEFORE UPDATE ON tenant_professor_step_events BEGIN
      SELECT RAISE(ABORT,'step event history is append-only');
    END;
    CREATE TRIGGER IF NOT EXISTS tenant_step_events_no_delete
      BEFORE DELETE ON tenant_professor_step_events BEGIN
      SELECT RAISE(ABORT,'step event history is append-only');
    END;
    """)


class TenantStepExecutionRepository:
    """Tenant-filtered step leases backed by the isolated tenant plan prototype."""

    def __init__(self, db: sqlite3.Connection, principal: RequestPrincipal):
        if not isinstance(db, sqlite3.Connection):
            raise TypeError("A caller-owned SQLite connection is required.")
        if not isinstance(principal, RequestPrincipal):
            raise TypeError("A verified RequestPrincipal is required.")
        self.db = db
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.principal = principal
        initialize_tenant_step_schema(db)

    def _auth(self, scope: str) -> str:
        authorize_tenant_resource(self.principal, self.principal.tenant_id, {scope})
        return self.principal.tenant_id

    @staticmethod
    def _validate_worker(worker_id: str, lease_seconds: int) -> None:
        if not isinstance(worker_id, str) or not worker_id.strip() or len(worker_id) > 128:
            raise ValueError("worker_id must be a non-empty string of at most 128 characters.")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 1 <= lease_seconds <= 900:
            raise ValueError("lease_seconds must be between 1 and 900.")

    def _seed_runs(self, tenant_id: str, plan_id: str) -> None:
        self.db.execute("""
          INSERT OR IGNORE INTO tenant_professor_step_runs
            (tenant_id,plan_id,step_id,state)
          SELECT tenant_id,plan_id,step_id,'pending'
          FROM tenant_professor_plan_steps WHERE tenant_id=? AND plan_id=?
        """, (tenant_id, plan_id))

    def _event(self, tenant_id, plan_id, step_id, kind, attempt, worker, token, details=None):
        self.db.execute("""
          INSERT INTO tenant_professor_step_events
            (tenant_id,plan_id,step_id,event_type,attempt_number,worker_id,
             fencing_token,details_json,created_at)
          VALUES(?,?,?,?,?,?,?,?,?)
        """, (tenant_id, plan_id, step_id, kind, attempt, worker, token,
              _json_payload(details or {}), _now_iso()))

    def _expire(self, tenant_id: str, plan_id: str, now: float) -> None:
        rows = self.db.execute("""
          SELECT step_id,attempt_number,worker_id,fencing_token
          FROM tenant_professor_step_runs
          WHERE tenant_id=? AND plan_id=? AND state='claimed' AND lease_expires_at<=?
        """, (tenant_id, plan_id, now)).fetchall()
        for row in rows:
            cur = self.db.execute("""
              UPDATE tenant_professor_step_runs
              SET state='recovery_required',worker_id=NULL,lease_expires_at=NULL,
                  updated_at=CURRENT_TIMESTAMP
              WHERE tenant_id=? AND plan_id=? AND step_id=? AND state='claimed'
                AND fencing_token=? AND lease_expires_at<=?
            """, (tenant_id, plan_id, row["step_id"], row["fencing_token"], now))
            if cur.rowcount:
                self._event(tenant_id, plan_id, row["step_id"], "lease_expired",
                            row["attempt_number"], row["worker_id"], row["fencing_token"],
                            {"decision":"recovery_required","automatic_replay":False})

    def claim_next_step(self, plan_id: str, worker_id: str,
                        lease_seconds: int = 60) -> TenantStepLease | None:
        tenant_id = self._auth("steps:claim")
        self._validate_worker(worker_id, lease_seconds)
        if not isinstance(plan_id, str) or not plan_id.strip() or len(plan_id) > 128:
            raise ValueError("plan_id must be a non-empty string of at most 128 characters.")
        now = time.time()
        try:
            self.db.execute("BEGIN IMMEDIATE")
            plan = self.db.execute("""
              SELECT state,plan_json FROM tenant_professor_plans
              WHERE tenant_id=? AND plan_id=?
            """, (tenant_id, plan_id)).fetchone()
            if plan is None:
                raise TenantStepNotFound("Plan step was not found.")
            if plan["state"] != "running":
                raise TenantStepPlanNotRunning("Tenant plan must be running before steps can be claimed.")
            cancellation_table = self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tenant_professor_cancellation_requests'"
            ).fetchone()
            if cancellation_table is not None:
                cancellation = self.db.execute(
                    "SELECT 1 FROM tenant_professor_cancellation_requests WHERE tenant_id=? AND plan_id=?",
                    (tenant_id, plan_id),
                ).fetchone()
                if cancellation is not None:
                    self.db.commit()
                    return None
            self._seed_runs(tenant_id, plan_id)
            self._expire(tenant_id, plan_id, now)
            plan_steps = {
                s["step_id"]: s for s in json.loads(plan["plan_json"])["steps"]
            }
            dependencies = {
                step_id: tuple(step.get("depends_on", ()))
                for step_id, step in plan_steps.items()
            }
            rows = self.db.execute("""
              SELECT r.step_id,r.attempt_number,r.fencing_token,p.risk
              FROM tenant_professor_step_runs r
              JOIN tenant_professor_plan_steps p
                ON p.tenant_id=r.tenant_id AND p.plan_id=r.plan_id AND p.step_id=r.step_id
              WHERE r.tenant_id=? AND r.plan_id=? AND r.state='pending'
              ORDER BY p.ordinal
            """, (tenant_id, plan_id)).fetchall()
            selected = None
            for row in rows:
                ready = True
                for dep in dependencies.get(row["step_id"], ()):
                    dep_row = self.db.execute("""
                      SELECT state FROM tenant_professor_step_runs
                      WHERE tenant_id=? AND plan_id=? AND step_id=?
                    """, (tenant_id, plan_id, dep)).fetchone()
                    if dep_row is None or dep_row["state"] != "succeeded":
                        ready = False
                        break
                if ready:
                    selected = row
                    break
            if selected is None:
                self.db.commit()
                return None
            step_contract = plan_steps.get(selected["step_id"], {})
            required_scopes = frozenset(step_contract.get("required_scopes", ()))
            missing_scopes = required_scopes - self.principal.scopes
            if missing_scopes:
                self.db.commit()
                raise TenantStepError(
                    "Worker lacks required step scopes: " + ", ".join(sorted(missing_scopes))
                )
            if selected["risk"] in {"external_side_effect", "privileged"}:
                self.db.commit()
                raise TenantStepError(
                    "External and privileged steps remain blocked pending verified, "
                    "action-bound authorisation.")
            attempt = selected["attempt_number"] + 1
            token = selected["fencing_token"] + 1
            expires = now + lease_seconds
            cur = self.db.execute("""
              UPDATE tenant_professor_step_runs
              SET state='claimed',attempt_number=?,worker_id=?,fencing_token=?,
                  lease_expires_at=?,updated_at=CURRENT_TIMESTAMP
              WHERE tenant_id=? AND plan_id=? AND step_id=? AND state='pending'
            """, (attempt, worker_id, token, expires, tenant_id, plan_id, selected["step_id"]))
            if cur.rowcount != 1:
                raise TenantStepConflict("Step was claimed concurrently.")
            self._event(tenant_id, plan_id, selected["step_id"], "claimed",
                        attempt, worker_id, token, {"lease_seconds":lease_seconds})
            self.db.commit()
            return TenantStepLease(tenant_id, plan_id, selected["step_id"],
                                   worker_id, attempt, token, expires)
        except Exception:
            if self.db.in_transaction:
                self.db.rollback()
            raise

    def heartbeat(self, lease: TenantStepLease, lease_seconds: int = 60) -> TenantStepLease:
        tenant_id = self._auth("steps:heartbeat")
        if not isinstance(lease, TenantStepLease) or lease.tenant_id != tenant_id:
            raise TenantStepConflict("Step lease is stale, expired or no longer owned.")
        self._validate_worker(lease.worker_id, lease_seconds)
        now = time.time()
        expires = now + lease_seconds
        try:
            self.db.execute("BEGIN IMMEDIATE")
            cur = self.db.execute("""
              UPDATE tenant_professor_step_runs
              SET lease_expires_at=?,updated_at=CURRENT_TIMESTAMP
              WHERE tenant_id=? AND plan_id=? AND step_id=? AND state='claimed'
                AND worker_id=? AND attempt_number=? AND fencing_token=? AND lease_expires_at>?
            """, (expires, tenant_id, lease.plan_id, lease.step_id, lease.worker_id,
                  lease.attempt_number, lease.fencing_token, now))
            if cur.rowcount != 1:
                raise TenantStepConflict("Step lease is stale, expired or no longer owned.")
            self._event(tenant_id, lease.plan_id, lease.step_id, "heartbeat",
                        lease.attempt_number, lease.worker_id, lease.fencing_token,
                        {"lease_seconds":lease_seconds})
            self.db.commit()
            return TenantStepLease(tenant_id, lease.plan_id, lease.step_id, lease.worker_id,
                                   lease.attempt_number, lease.fencing_token, expires)
        except Exception:
            if self.db.in_transaction: self.db.rollback()
            raise

    def complete(self, lease: TenantStepLease, *, result: Any = None,
                 error_code: str | None = None) -> TenantStepRecord:
        tenant_id = self._auth("steps:complete")
        if not isinstance(lease, TenantStepLease) or lease.tenant_id != tenant_id:
            raise TenantStepConflict("Step lease is stale, expired or no longer owned.")
        if error_code is not None and (not isinstance(error_code, str)
                or not error_code.strip() or len(error_code) > 128):
            raise ValueError("error_code must be a non-empty string of at most 128 characters.")
        if error_code is not None and result is not None:
            raise ValueError("Provide either a result or an error_code, not both.")
        result_json = _json_payload(result) if error_code is None else None
        target = "failed" if error_code is not None else "succeeded"
        now = time.time()
        try:
            self.db.execute("BEGIN IMMEDIATE")
            cur = self.db.execute("""
              UPDATE tenant_professor_step_runs
              SET state=?,worker_id=NULL,lease_expires_at=NULL,result_json=?,error_code=?,
                  updated_at=CURRENT_TIMESTAMP
              WHERE tenant_id=? AND plan_id=? AND step_id=? AND state='claimed'
                AND worker_id=? AND attempt_number=? AND fencing_token=? AND lease_expires_at>?
            """, (target, result_json, error_code, tenant_id, lease.plan_id, lease.step_id,
                  lease.worker_id, lease.attempt_number, lease.fencing_token, now))
            if cur.rowcount != 1:
                raise TenantStepConflict("Step lease is stale, expired or no longer owned.")
            self._event(tenant_id, lease.plan_id, lease.step_id, target,
                        lease.attempt_number, lease.worker_id, lease.fencing_token,
                        {"error_code":error_code} if error_code else {"result_recorded":result is not None})
            row = self.db.execute("""
              SELECT r.*,p.ordinal,p.capability,p.capability_version,p.risk
              FROM tenant_professor_step_runs r JOIN tenant_professor_plan_steps p
                ON p.tenant_id=r.tenant_id AND p.plan_id=r.plan_id AND p.step_id=r.step_id
              WHERE r.tenant_id=? AND r.plan_id=? AND r.step_id=?
            """, (tenant_id, lease.plan_id, lease.step_id)).fetchone()
            self.db.commit()
            return self._record(row)
        except Exception:
            if self.db.in_transaction: self.db.rollback()
            raise

    def resolve_recovery_as_failed(
        self, plan_id: str, step_id: str, *,
        expected_fencing_token: int, reason: str,
    ) -> TenantStepRecord:
        """Resolve uncertain work to terminal failure; never authorise replay.

        This is an explicit tenant-operator decision. The expected fencing token
        prevents a stale review from resolving a different execution attempt.
        """
        tenant_id = self._auth("steps:recover")
        if not isinstance(plan_id, str) or not plan_id.strip() or len(plan_id) > 128:
            raise ValueError("plan_id must be a non-empty bounded string.")
        if not isinstance(step_id, str) or not step_id.strip() or len(step_id) > 128:
            raise ValueError("step_id must be a non-empty bounded string.")
        if (isinstance(expected_fencing_token, bool)
                or not isinstance(expected_fencing_token, int)
                or expected_fencing_token < 1):
            raise ValueError("expected_fencing_token must be a positive integer.")
        if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 500:
            raise ValueError("reason must contain 1 to 500 characters.")
        reason = reason.strip()
        now = time.time()
        try:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("""
              SELECT r.*,p.ordinal,p.capability,p.capability_version,p.risk
              FROM tenant_professor_step_runs r JOIN tenant_professor_plan_steps p
                ON p.tenant_id=r.tenant_id AND p.plan_id=r.plan_id AND p.step_id=r.step_id
              WHERE r.tenant_id=? AND r.plan_id=? AND r.step_id=?
            """, (tenant_id, plan_id, step_id)).fetchone()
            if row is None:
                raise TenantStepNotFound("Plan step was not found.")
            if row["state"] != "recovery_required":
                raise TenantStepConflict("Only recovery-required work can be resolved.")
            if row["fencing_token"] != expected_fencing_token:
                raise TenantStepConflict("Recovery decision refers to a stale fencing token.")

            cur = self.db.execute("""
              UPDATE tenant_professor_step_runs
              SET state='failed',worker_id=NULL,lease_expires_at=NULL,
                  result_json=NULL,error_code='operator_marked_failed',
                  updated_at=CURRENT_TIMESTAMP
              WHERE tenant_id=? AND plan_id=? AND step_id=?
                AND state='recovery_required' AND fencing_token=?
            """, (tenant_id, plan_id, step_id, expected_fencing_token))
            if cur.rowcount != 1:
                raise TenantStepConflict("Recovery state changed before the decision was committed.")
            self._event(
                tenant_id, plan_id, step_id, "failed", row["attempt_number"], None,
                expected_fencing_token,
                {
                    "decision": "operator_marked_failed",
                    "reason": reason,
                    "actor_issuer": self.principal.issuer,
                    "actor_subject": self.principal.subject,
                    "automatic_replay": False,
                },
            )
            resolved = self.db.execute("""
              SELECT r.*,p.ordinal,p.capability,p.capability_version,p.risk
              FROM tenant_professor_step_runs r JOIN tenant_professor_plan_steps p
                ON p.tenant_id=r.tenant_id AND p.plan_id=r.plan_id AND p.step_id=r.step_id
              WHERE r.tenant_id=? AND r.plan_id=? AND r.step_id=?
            """, (tenant_id, plan_id, step_id)).fetchone()
            self.db.commit()
            return self._record(resolved)
        except Exception:
            if self.db.in_transaction:
                self.db.rollback()
            raise

    def dependency_results(self, plan_id: str, step_id: str) -> dict[str, Any]:
        """Return only completed direct-dependency outputs for this tenant and step.

        Plan dependencies are read from the persisted immutable plan contract;
        callers cannot nominate arbitrary source steps. All dependencies must
        have succeeded, and the combined hand-off is capped at 64 KiB.
        """
        tenant_id = self._auth("steps:read")
        if not isinstance(plan_id, str) or not plan_id.strip() or len(plan_id) > 128:
            raise ValueError("plan_id must be a non-empty bounded string.")
        if not isinstance(step_id, str) or not step_id.strip() or len(step_id) > 128:
            raise ValueError("step_id must be a non-empty bounded string.")
        plan = self.db.execute(
            "SELECT plan_json FROM tenant_professor_plans WHERE tenant_id=? AND plan_id=?",
            (tenant_id, plan_id),
        ).fetchone()
        if plan is None:
            raise TenantStepNotFound("Plan step was not found.")
        contract = json.loads(plan["plan_json"])
        step = next((item for item in contract["steps"] if item["step_id"] == step_id), None)
        if step is None:
            raise TenantStepNotFound("Plan step was not found.")
        dependencies = tuple(step.get("depends_on", ()))
        if not dependencies:
            return {}
        placeholders = ",".join("?" for _ in dependencies)
        rows = self.db.execute(
            f"""SELECT r.step_id,r.state,r.result_json,p.capability
                FROM tenant_professor_step_runs r
                JOIN tenant_professor_plan_steps p
                  ON p.tenant_id=r.tenant_id AND p.plan_id=r.plan_id AND p.step_id=r.step_id
                WHERE r.tenant_id=? AND r.plan_id=? AND r.step_id IN ({placeholders})""",
            (tenant_id, plan_id, *dependencies),
        ).fetchall()
        by_id = {row["step_id"]: row for row in rows}
        if len(by_id) != len(dependencies) or any(
            by_id[item]["state"] != "succeeded" or by_id[item]["result_json"] is None
            for item in dependencies
        ):
            raise TenantStepConflict("Every direct dependency must succeed before outputs can be handed off.")
        results = {item: json.loads(by_id[item]["result_json"]) for item in dependencies}

        # If a direct dependency is an evidence bundle, use its latest
        # append-only reviewer revision for downstream evaluation/reporting.
        # The immutable execution result remains unchanged. Reading a reviewed
        # revision is itself permission-gated; never silently fall back when a
        # revision exists but this principal lacks review access.
        table = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tenant_evidence_reviews'"
        ).fetchone()
        if table is not None:
            for dependency in dependencies:
                if by_id[dependency]["capability"] != "research.evidence.bundle":
                    continue
                reviewed = self.db.execute("""
                  SELECT bundle_json FROM tenant_evidence_reviews
                  WHERE tenant_id=? AND plan_id=? AND bundle_step_id=?
                  ORDER BY review_id DESC LIMIT 1
                """, (tenant_id, plan_id, dependency)).fetchone()
                if reviewed is None:
                    continue
                authorize_tenant_resource(
                    self.principal, tenant_id, {"evidence:review"}
                )
                results[dependency] = json.loads(reviewed["bundle_json"])

        _json_payload(results, max_bytes=65_536)
        return results

    def get_step(self, plan_id: str, step_id: str) -> TenantStepRecord:
        tenant_id = self._auth("steps:read")
        row = self.db.execute("""
          SELECT r.*,p.ordinal,p.capability,p.capability_version,p.risk
          FROM tenant_professor_step_runs r JOIN tenant_professor_plan_steps p
            ON p.tenant_id=r.tenant_id AND p.plan_id=r.plan_id AND p.step_id=r.step_id
          WHERE r.tenant_id=? AND r.plan_id=? AND r.step_id=?
        """, (tenant_id, plan_id, step_id)).fetchone()
        if row is None:
            raise TenantStepNotFound("Plan step was not found.")
        return self._record(row)

    def list_steps(self, plan_id: str) -> tuple[TenantStepRecord, ...]:
        tenant_id = self._auth("steps:read")
        with self.db:
            self._seed_runs(tenant_id, plan_id)
        rows = self.db.execute("""
          SELECT r.*,p.ordinal,p.capability,p.capability_version,p.risk
          FROM tenant_professor_step_runs r JOIN tenant_professor_plan_steps p
            ON p.tenant_id=r.tenant_id AND p.plan_id=r.plan_id AND p.step_id=r.step_id
          WHERE r.tenant_id=? AND r.plan_id=? ORDER BY p.ordinal
        """, (tenant_id, plan_id)).fetchall()
        if not rows:
            raise TenantStepNotFound("Plan step was not found.")
        return tuple(self._record(row) for row in rows)

    def list_events(self, plan_id: str, step_id: str, *, limit: int = 100) -> tuple[TenantStepEvent, ...]:
        tenant_id = self._auth("steps:read")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500.")
        exists = self.db.execute("""
          SELECT 1 FROM tenant_professor_step_runs
          WHERE tenant_id=? AND plan_id=? AND step_id=?
        """, (tenant_id, plan_id, step_id)).fetchone()
        if exists is None:
            raise TenantStepNotFound("Plan step was not found.")
        rows = self.db.execute("""
          SELECT * FROM (
            SELECT * FROM tenant_professor_step_events
            WHERE tenant_id=? AND plan_id=? AND step_id=?
            ORDER BY event_id DESC LIMIT ?
          ) ORDER BY event_id ASC
        """, (tenant_id, plan_id, step_id, limit)).fetchall()
        return tuple(TenantStepEvent(r["tenant_id"],r["plan_id"],r["step_id"],r["event_type"],
                    r["attempt_number"],r["worker_id"],r["fencing_token"],
                    json.loads(r["details_json"]),r["created_at"]) for r in rows)

    @staticmethod
    def _record(row) -> TenantStepRecord:
        return TenantStepRecord(row["tenant_id"],row["plan_id"],row["step_id"],row["ordinal"],
            row["capability"],row["capability_version"],row["risk"],row["state"],
            row["attempt_number"],row["fencing_token"],row["worker_id"],row["lease_expires_at"],
            json.loads(row["result_json"]) if row["result_json"] is not None else None,
            row["error_code"])
