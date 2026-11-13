from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest

from atlas_engine import storage
from atlas_engine.task_manager import TaskManager


def _manager(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "task-recovery.db"))
    storage.init_db()
    return TaskManager(storage)


def test_task_attempt_schema_migration_is_idempotent(tmp_path, monkeypatch):
    _manager(tmp_path, monkeypatch)
    storage.init_db()
    conn = storage.get_connection()
    try:
        tables = {row["name"] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "task_attempts" in tables
    finally:
        conn.close()


def test_claim_with_lease_is_atomic_and_fenced(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Lease claim", "Only one worker may own this task", [])
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(
            lambda i: storage.claim_task_with_lease(task.id, f"worker-{i}", 30),
            range(8),
        ))
    successful = [claim for claim in claims if claim is not None]
    assert len(successful) == 1
    claim = successful[0]
    assert claim["fencing_token"] == 1
    assert claim["attempt_number"] == 1
    persisted = manager.get_task(task.id)
    assert persisted.status == "running"
    assert persisted.attempts == 1
    assert len(storage.get_task_attempts(task.id)) == 1


def test_heartbeat_requires_matching_live_owner_and_fencing_token(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Heartbeat", "Only the lease owner may renew", [])
    claim = storage.claim_task_with_lease(task.id, "worker-a", 30)
    assert claim is not None
    assert not storage.heartbeat_task_attempt(
        task.id, claim["attempt_id"], "worker-b", claim["fencing_token"], 30
    )
    assert not storage.heartbeat_task_attempt(
        task.id, claim["attempt_id"], "worker-a", claim["fencing_token"] + 1, 30
    )
    assert storage.heartbeat_task_attempt(
        task.id, claim["attempt_id"], "worker-a", claim["fencing_token"], 30
    )


def test_expired_lease_requires_recovery_and_is_never_auto_requeued(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Crash recovery", "Do not rerun uncertain work", [])
    claim = storage.claim_task_with_lease(task.id, "worker-crashed", 5)
    assert claim is not None
    future = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
    assert storage.mark_expired_task_attempts(now=future) == 1
    pending = storage.list_recovery_required_attempts()
    assert len(pending) == 1
    assert pending[0]["attempt_id"] == claim["attempt_id"]
    assert pending[0]["state"] == "recovery_required"
    assert manager.get_task(task.id).status == "running"
    assert storage.claim_task_with_lease(task.id, "worker-retry", 30) is None
    assert len(storage.get_task_attempts(task.id)) == 1


def test_expired_lease_cannot_be_renewed_even_before_expiry_scan(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Expired heartbeat", "Expired lease cannot revive itself", [])
    claim = storage.claim_task_with_lease(task.id, "worker-a", 5)
    assert claim is not None
    conn = storage.get_connection()
    try:
        conn.execute(
            "UPDATE task_attempts SET lease_expires_at = ? WHERE attempt_id = ?",
            ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), claim["attempt_id"]),
        )
        conn.commit()
    finally:
        conn.close()
    assert not storage.heartbeat_task_attempt(
        task.id, claim["attempt_id"], "worker-a", claim["fencing_token"], 30
    )


def test_recovery_required_attempt_blocks_claim_even_if_task_is_reset_pending(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Held recovery", "Manual reset must not bypass recovery", [])
    claim = storage.claim_task_with_lease(task.id, "worker-lost", 5)
    assert claim is not None
    future = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
    assert storage.mark_expired_task_attempts(now=future) == 1
    # Simulate an accidental/manual task status reset. The recovery hold must still win.
    storage.update_task(task.id, {"status": "pending", "updated_at": storage.now_isoformat()})
    assert storage.claim_task_with_lease(task.id, "worker-new", 30) is None
    assert storage.list_recovery_required_attempts()[0]["attempt_id"] == claim["attempt_id"]



def test_task_api_completes_lease_and_evaluation_atomically(tmp_path, monkeypatch):
    from atlas_engine.task_manager import TaskAPI
    from atlas_engine.evaluator import Evaluator

    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task(
        "Leased execution", "Complete task and lease together",
        [{"field": "value", "operator": "==", "expected_value": 7}],
    )

    class Executor:
        @staticmethod
        def execute(_payload):
            return {"value": 7}

    class Memory:
        @staticmethod
        def get_relevant_lessons(_description):
            return []

    api = TaskAPI(manager, Executor(), Evaluator(), Memory(), None, None)
    response = api.run_task(task.id)

    assert response["status"] == "passed"
    attempts = storage.get_task_attempts(task.id)
    assert len(attempts) == 1
    assert attempts[0]["state"] == "completed"
    assert attempts[0]["finished_at"] is not None
    assert len(storage.get_evaluations_for_task(task.id)) == 1


def test_task_api_execution_failure_completes_lease_with_failure_evaluation(tmp_path, monkeypatch):
    from atlas_engine.task_manager import TaskAPI
    from atlas_engine.evaluator import Evaluator

    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Leased failure", "Failure must be audited", [])

    class BrokenExecutor:
        @staticmethod
        def execute(_payload):
            raise RuntimeError("private exception detail")

    class Memory:
        @staticmethod
        def get_relevant_lessons(_description):
            return []

    api = TaskAPI(manager, BrokenExecutor(), Evaluator(), Memory(), None, None)
    response = api.run_task(task.id)

    assert response["status"] == "failed"
    attempts = storage.get_task_attempts(task.id)
    assert len(attempts) == 1
    assert attempts[0]["state"] == "failed"
    assert len(storage.get_evaluations_for_task(task.id)) == 1
    assert "private exception detail" not in str(response)



def test_recovery_routes_are_authenticated_and_never_auto_retry(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app as app_module

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "recovery-routes.db"))
    monkeypatch.setattr(app_module, "API_REQUIRE_AUTH", True)
    monkeypatch.setattr(app_module, "API_KEY", "test-secret")
    storage.init_db()
    task = app_module.manager.create_task("API recovery", "Inspect an expired lease", [])
    claim = storage.claim_task_with_lease(task.id, "worker-gone", 5)
    assert claim is not None
    expired = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    conn = storage.get_connection()
    try:
        conn.execute(
            "UPDATE task_attempts SET lease_expires_at = ? WHERE attempt_id = ?",
            (expired, claim["attempt_id"]),
        )
        conn.commit()
    finally:
        conn.close()

    client = TestClient(app_module.app)
    assert client.get("/tasks/recovery-required").status_code == 401
    headers = {"X-API-Key": "test-secret"}
    scan = client.post("/tasks/recovery/scan", headers=headers)
    assert scan.status_code == 200
    assert scan.json()["marked_for_recovery"] == 1
    listed = client.get("/tasks/recovery-required", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["attempt_id"] == claim["attempt_id"]
    assert app_module.manager.get_task(task.id).status == "running"
    assert storage.claim_task_with_lease(task.id, "worker-retry", 30) is None



def test_recovery_retry_requires_explicit_safety_and_reconciliation(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Retry gate", "Do not retry uncertain work", [])
    claim = storage.claim_task_with_lease(task.id, "worker-lost", 5)
    assert claim is not None
    future = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
    assert storage.mark_expired_task_attempts(now=future) == 1

    import pytest
    with pytest.raises(ValueError, match="Retry requires explicit confirmation"):
        storage.resolve_task_recovery(
            task.id, claim["attempt_id"], "retry", "operator", "Not yet verified"
        )

    assert storage.resolve_task_recovery(
        task.id, claim["attempt_id"], "retry", "operator",
        "Confirmed local operation is safe to replay",
        retry_safe=True, side_effects_reconciled=True,
    )
    assert manager.get_task(task.id).status == "pending"
    attempts = storage.get_task_attempts(task.id)
    assert attempts[0]["state"] == "abandoned"
    decisions = storage.list_task_recovery_decisions(task.id)
    assert len(decisions) == 1
    assert decisions[0]["action"] == "retry"
    assert decisions[0]["retry_safe"] == 1
    assert decisions[0]["side_effects_reconciled"] == 1
    next_claim = storage.claim_task_with_lease(task.id, "worker-retry", 30)
    assert next_claim["attempt_number"] == 2
    assert next_claim["fencing_token"] == 2


def test_recovery_mark_failed_writes_task_evaluation_and_decision_atomically(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Mark failed", "Persist operator decision", [])
    claim = storage.claim_task_with_lease(task.id, "worker-lost", 5)
    assert claim is not None
    future = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
    assert storage.mark_expired_task_attempts(now=future) == 1

    assert storage.resolve_task_recovery(
        task.id, claim["attempt_id"], "mark_failed", "operator",
        "Worker stopped and no completed result could be recovered",
    )
    assert manager.get_task(task.id).status == "failed"
    attempts = storage.get_task_attempts(task.id)
    assert attempts[0]["state"] == "failed"
    evaluations = storage.get_evaluations_for_task(task.id)
    assert len(evaluations) == 1
    assert evaluations[0]["method"] == "recovery_operator_decision"
    assert storage.list_task_recovery_decisions(task.id)[0]["action"] == "mark_failed"


def test_recovery_decision_cannot_be_applied_twice(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Single decision", "Recovery decisions are one-shot", [])
    claim = storage.claim_task_with_lease(task.id, "worker-lost", 5)
    future = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
    assert storage.mark_expired_task_attempts(now=future) == 1
    assert storage.resolve_task_recovery(
        task.id, claim["attempt_id"], "mark_failed", "operator", "Confirmed failed"
    )
    assert not storage.resolve_task_recovery(
        task.id, claim["attempt_id"], "mark_failed", "operator", "Duplicate decision"
    )
    assert len(storage.list_task_recovery_decisions(task.id)) == 1



def test_recovery_lease_survives_database_reinitialization(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Restart recovery", "Lease records survive process restart", [])
    claim = storage.claim_task_with_lease(task.id, "worker-before-restart", 5)
    assert claim is not None

    storage.init_db()
    future = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
    assert storage.mark_expired_task_attempts(now=future) == 1
    recovered = storage.list_recovery_required_attempts()
    assert len(recovered) == 1
    assert recovered[0]["attempt_id"] == claim["attempt_id"]
    assert manager.get_task(task.id).status == "running"


def test_authenticated_recovery_decision_route_records_explicit_retry(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app as app_module

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "recovery-decision-route.db"))
    monkeypatch.setattr(app_module, "API_REQUIRE_AUTH", True)
    monkeypatch.setattr(app_module, "API_KEY", "test-secret")
    storage.init_db()
    task = app_module.manager.create_task("Route retry", "Retry only after explicit safety checks", [])
    claim = storage.claim_task_with_lease(task.id, "worker-stopped", 5)
    assert claim is not None
    expired = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    conn = storage.get_connection()
    try:
        conn.execute(
            "UPDATE task_attempts SET lease_expires_at = ? WHERE attempt_id = ?",
            (expired, claim["attempt_id"]),
        )
        conn.commit()
    finally:
        conn.close()
    assert storage.mark_expired_task_attempts() == 1

    client = TestClient(app_module.app)
    headers = {"X-API-Key": "test-secret"}
    response = client.post(
        f"/tasks/{task.id}/recovery-decision",
        headers=headers,
        json={
            "attempt_id": claim["attempt_id"],
            "action": "retry",
            "actor": "operator",
            "reason": "Confirmed no external side effect occurred",
            "retry_safe": True,
            "side_effects_reconciled": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "recovery_decision_recorded"
    assert response.json()["task"]["status"] == "pending"
    assert response.json()["decisions"][0]["action"] == "retry"


def test_task_api_does_not_report_failure_when_failure_persistence_raises(tmp_path, monkeypatch):
    from atlas_engine.task_manager import TaskAPI
    from atlas_engine.evaluator import Evaluator

    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Unconfirmed failure", "Persistence failure must not be hidden", [])

    class BrokenExecutor:
        @staticmethod
        def execute(_payload):
            raise RuntimeError("private execution detail")

    class Memory:
        @staticmethod
        def get_relevant_lessons(_description):
            return []

    def fail_to_persist(*_args, **_kwargs):
        raise OSError("private database detail")

    monkeypatch.setattr(manager, "complete_with_evaluation", fail_to_persist)
    api = TaskAPI(manager, BrokenExecutor(), Evaluator(), Memory(), None, None)
    response = api.run_task(task.id)

    assert response["status"] == "outcome_unconfirmed"
    assert "private database detail" not in str(response)
    assert "private execution detail" not in str(response)
    assert manager.get_task(task.id).status == "running"
    attempts = storage.get_task_attempts(task.id)
    assert len(attempts) == 1
    assert attempts[0]["state"] == "active"
    assert storage.get_evaluations_for_task(task.id) == []


def test_cancellation_schema_is_idempotent_and_survives_reinitialization(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Cancellation schema", "Persist cancel request", [])
    claim = storage.claim_task_with_lease(task.id, "worker-a", 30)
    assert claim is not None
    first = storage.request_task_cancellation(
        task.id, claim["attempt_id"], "operator", "Stop this task"
    )
    assert first is not None
    storage.init_db()
    restored = storage.get_task_cancellation(task.id, claim["attempt_id"])
    assert restored is not None
    assert restored["cancellation_id"] == first["cancellation_id"]
    assert restored["state"] == "requested"


def test_cancellation_request_requires_live_attempt_and_is_idempotent(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Cancellation request", "Only current worker can be cancelled", [])
    claim = storage.claim_task_with_lease(task.id, "worker-a", 30)
    assert claim is not None
    first = storage.request_task_cancellation(
        task.id, claim["attempt_id"], "operator", "Requested stop"
    )
    second = storage.request_task_cancellation(
        task.id, claim["attempt_id"], "operator", "Duplicate request"
    )
    assert first["cancellation_id"] == second["cancellation_id"]
    assert second["state"] == "requested"
    assert storage.request_task_cancellation(
        task.id, "unknown-attempt", "operator", "Unknown attempt"
    ) is None


def test_cancellation_wins_completion_race_and_acknowledges_atomically(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Cancellation race", "Cancellation must beat task commit", [])
    claim = storage.claim_task_with_lease(task.id, "worker-a", 30)
    assert claim is not None
    cancellation = storage.request_task_cancellation(
        task.id, claim["attempt_id"], "operator", "Cancel before commit"
    )
    assert cancellation["state"] == "requested"

    record = {
        "id": "evaluation-race",
        "task_id": task.id,
        "passed": True,
        "score": 1.0,
        "reasons_json": "[]",
        "missing_requirements_json": "[]",
        "method": "test",
        "created_at": storage.now_isoformat(),
    }
    assert not storage.complete_task_with_evaluation(
        task.id, record, "passed", {"value": 1}, attempt=claim
    )
    assert manager.get_task(task.id).status == "running"
    assert storage.get_task_attempts(task.id)[0]["state"] == "active"

    cancelled_record = {
        "id": "evaluation-cancelled",
        "task_id": task.id,
        "method": "cancelled",
    }
    assert storage.acknowledge_task_cancellation(task.id, claim, cancelled_record)
    assert manager.get_task(task.id).status == "failed"
    assert manager.get_task(task.id).result == {"error_type": "TaskCancelled"}
    assert storage.get_task_attempts(task.id)[0]["error_type"] == "TaskCancelled"
    assert storage.get_task_attempts(task.id)[0]["state"] == "failed"
    assert storage.get_evaluations_for_task(task.id)[0]["method"] == "cancelled"
    assert storage.get_task_cancellation(task.id, claim["attempt_id"])["state"] == "acknowledged"

    # Even an accidental status reset cannot revive a cancelled task.
    storage.update_task(task.id, {"status": "pending", "updated_at": storage.now_isoformat()})
    assert storage.claim_task_with_lease(task.id, "worker-b", 30) is None


def test_stale_worker_cannot_acknowledge_cancellation(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Stale cancellation", "Fence cancellation acknowledgements", [])
    claim = storage.claim_task_with_lease(task.id, "worker-a", 30)
    assert claim is not None
    storage.request_task_cancellation(task.id, claim["attempt_id"], "operator", "Stop")
    stale = {**claim, "fencing_token": claim["fencing_token"] + 1}
    assert not storage.acknowledge_task_cancellation(
        task.id, stale,
        {"id": "evaluation-stale", "task_id": task.id, "method": "cancelled"},
    )
    assert storage.get_task_cancellation(task.id, claim["attempt_id"])["state"] == "requested"
    assert manager.get_task(task.id).status == "running"


def test_expired_worker_moves_pending_cancellation_to_recovery_required(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Expired cancellation", "Do not claim cancellation without worker proof", [])
    claim = storage.claim_task_with_lease(task.id, "worker-lost", 5)
    assert claim is not None
    storage.request_task_cancellation(task.id, claim["attempt_id"], "operator", "Stop")
    future = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
    assert storage.mark_expired_task_attempts(now=future) == 1
    assert storage.get_task_cancellation(task.id, claim["attempt_id"])["state"] == "requires_recovery"
    assert storage.get_task_attempts(task.id)[0]["state"] == "recovery_required"
    assert manager.get_task(task.id).status == "running"


def test_task_api_acknowledges_cancellation_after_local_executor_safe_point(tmp_path, monkeypatch):
    from atlas_engine.task_manager import TaskAPI
    from atlas_engine.evaluator import Evaluator

    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Cooperative cancel", "Cancellation during bounded local work", [])

    class Executor:
        def execute(self, _payload):
            attempt = storage.get_task_attempts(task.id)[0]
            storage.request_task_cancellation(
                task.id, attempt["attempt_id"], "operator", "Stop after current safe unit"
            )
            return {"value": "computed-but-not-committed"}

    class Memory:
        @staticmethod
        def get_relevant_lessons(_description):
            return []

    api = TaskAPI(manager, Executor(), Evaluator(), Memory(), None, None)
    response = api.run_task(task.id)
    assert response["status"] == "cancelled"
    assert storage.get_task_cancellation(task.id)["state"] == "acknowledged"
    assert storage.get_task_attempts(task.id)[0]["state"] == "failed"
    assert storage.get_evaluations_for_task(task.id)[0]["method"] == "cancelled"


def test_completed_task_cannot_be_cancelled_after_commit(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Too late cancellation", "Completion wins if committed first", [])
    claim = storage.claim_task_with_lease(task.id, "worker-a", 30)
    assert claim is not None
    record = {
        "id": "evaluation-complete-first",
        "task_id": task.id,
        "passed": True,
        "score": 1.0,
        "reasons_json": "[]",
        "missing_requirements_json": "[]",
        "method": "test",
        "created_at": storage.now_isoformat(),
    }
    assert storage.complete_task_with_evaluation(
        task.id, record, "passed", {"value": 1}, attempt=claim
    )
    late = storage.request_task_cancellation(
        task.id, claim["attempt_id"], "operator", "Too late"
    )
    assert late is not None
    assert late["state"] == "too_late"


def test_cancellation_route_is_authenticated_and_persists_request(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app as app_module

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "cancellation-route.db"))
    monkeypatch.setattr(app_module, "API_REQUIRE_AUTH", True)
    monkeypatch.setattr(app_module, "API_KEY", "test-secret")
    storage.init_db()
    task = app_module.manager.create_task("API cancellation", "Authenticated cancellation", [])
    claim = storage.claim_task_with_lease(task.id, "worker-api", 30)
    assert claim is not None

    client = TestClient(app_module.app)
    payload = {
        "attempt_id": claim["attempt_id"],
        "actor": "operator",
        "reason": "User requested cancellation",
    }
    assert client.post(f"/tasks/{task.id}/cancel", json=payload).status_code == 401
    response = client.post(
        f"/tasks/{task.id}/cancel",
        headers={"X-API-Key": "test-secret"},
        json=payload,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "requested"
    assert client.get(
        f"/tasks/{task.id}/cancellation",
        headers={"X-API-Key": "test-secret"},
    ).json()["state"] == "requested"


def test_expired_lease_cancellation_is_recorded_as_recovery_required(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Late cancellation", "Expired lease cannot be cancelled by a dead worker", [])
    claim = storage.claim_task_with_lease(task.id, "worker-gone", 5)
    assert claim is not None
    expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    conn = storage.get_connection()
    try:
        conn.execute(
            "UPDATE task_attempts SET lease_expires_at = ? WHERE attempt_id = ?",
            (expired, claim["attempt_id"]),
        )
        conn.commit()
    finally:
        conn.close()
    cancellation = storage.request_task_cancellation(
        task.id, claim["attempt_id"], "operator", "Cancel but worker is gone"
    )
    assert cancellation is not None
    assert cancellation["state"] == "requires_recovery"
    assert manager.get_task(task.id).status == "running"


def _verified_retry_contract():
    return {
        "capability_name": "test.read_only",
        "version": "1",
        "idempotent": True,
        "side_effects_declared": True,
        "duplicate_suppression_verified": True,
        "verification_evidence": "tests/test_task_recovery.py::test_fake_provider_deduplicates",
        "retryable_error_codes": ["temporary_unavailable"],
    }


def _retry_evaluation(task_id, evaluation_id="evaluation-retry"):
    return {
        "id": evaluation_id,
        "task_id": task_id,
        "passed": False,
        "score": 0.0,
        "reasons_json": '["temporary provider outage"]',
        "missing_requirements_json": '["operation completed"]',
        "method": "transient_execution_error",
    }


def _schedule_retry(task_id, claim, *, due_seconds=10, deadline_seconds=60, max_attempts=3):
    now = datetime.now(timezone.utc)
    return storage.persist_task_retry_schedule(
        task_id,
        claim,
        _retry_evaluation(task_id),
        capability_contract=_verified_retry_contract(),
        policy_snapshot={
            "max_attempts": max_attempts,
            "per_attempt_timeout_seconds": 30,
            "total_deadline_seconds": 90,
            "base_delay_seconds": 1,
            "max_delay_seconds": 15,
        },
        error_code="temporary_unavailable",
        idempotency_key=f"task:{task_id}:attempt:{claim['attempt_number']}",
        due_at=(now + timedelta(seconds=due_seconds)).isoformat(),
        deadline_at=(now + timedelta(seconds=deadline_seconds)).isoformat(),
    )


def test_retry_schedule_is_durable_bounded_and_claimed_only_when_due(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Durable retry", "Retry only after due time", [])
    claim = storage.claim_task_with_lease(task.id, "worker-a", 30)
    assert claim is not None
    schedule = _schedule_retry(task.id, claim)
    assert schedule is not None
    assert schedule["state"] == "scheduled"
    assert manager.get_task(task.id).status == "pending"
    assert storage.get_task_attempts(task.id)[0]["state"] == "failed"
    assert storage.get_evaluations_for_task(task.id)[0]["method"] == "transient_execution_error"

    storage.init_db()
    schedules = storage.list_task_retry_schedules(task.id)
    assert len(schedules) == 1
    assert schedules[0]["schedule_id"] == schedule["schedule_id"]
    assert schedules[0]["state"] == "scheduled"
    assert storage.claim_task_with_lease(task.id, "too-early", 30) is None

    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    conn = storage.get_connection()
    try:
        conn.execute(
            "UPDATE task_retry_schedules SET due_at = ? WHERE schedule_id = ?",
            (past, schedule["schedule_id"]),
        )
        conn.commit()
    finally:
        conn.close()
    retry_claim = storage.claim_task_with_lease(task.id, "worker-b", 30)
    assert retry_claim is not None
    assert retry_claim["attempt_number"] == 2
    stored = storage.list_task_retry_schedules(task.id)[0]
    assert stored["state"] == "claimed"
    assert stored["claimed_attempt_id"] == retry_claim["attempt_id"]


def test_retry_schedule_requires_verified_capability_and_allowlisted_error(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Retry contract", "Reject unverified retry contract", [])
    claim = storage.claim_task_with_lease(task.id, "worker-a", 30)
    assert claim is not None
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    common = dict(
        task_id=task.id,
        attempt=claim,
        evaluation_record=_retry_evaluation(task.id),
        policy_snapshot={"max_attempts": 3},
        error_code="temporary_unavailable",
        idempotency_key="stable-key",
        due_at=(now + timedelta(seconds=5)).isoformat(),
        deadline_at=(now + timedelta(seconds=30)).isoformat(),
    )
    unsafe = _verified_retry_contract()
    unsafe["duplicate_suppression_verified"] = False
    with pytest.raises(ValueError, match="Duplicate suppression"):
        storage.persist_task_retry_schedule(**common, capability_contract=unsafe)
    unsafe = _verified_retry_contract()
    with pytest.raises(ValueError, match="not allowlisted"):
        storage.persist_task_retry_schedule(
            **{**common, "error_code": "unknown"}, capability_contract=unsafe
        )
    assert manager.get_task(task.id).status == "running"
    assert storage.get_task_attempts(task.id)[0]["state"] == "active"


def test_retry_schedule_is_blocked_by_cancellation_and_can_be_cancelled_before_due(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Cancel retry", "Cancellation blocks future retry", [])
    claim = storage.claim_task_with_lease(task.id, "worker-a", 30)
    assert claim is not None
    schedule = _schedule_retry(task.id, claim, due_seconds=20)
    assert schedule is not None

    cancellation = storage.request_task_cancellation(
        task.id, claim["attempt_id"], "operator", "Cancel scheduled retry"
    )
    assert cancellation is not None
    assert cancellation["state"] == "acknowledged"
    assert storage.list_task_retry_schedules(task.id)[0]["state"] == "cancelled"
    assert storage.claim_task_with_lease(task.id, "worker-b", 30) is None


def test_retry_schedule_expires_at_deadline_and_cannot_be_claimed(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Expire retry", "No retry after deadline", [])
    claim = storage.claim_task_with_lease(task.id, "worker-a", 30)
    assert claim is not None
    schedule = _schedule_retry(task.id, claim, due_seconds=5, deadline_seconds=20)
    assert schedule is not None
    future = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
    assert storage.expire_task_retry_schedules(now=future) == 1
    assert storage.list_task_retry_schedules(task.id)[0]["state"] == "expired"
    assert storage.claim_task_with_lease(task.id, "worker-b", 30) is None


def test_retry_schedule_rejects_attempt_count_beyond_policy(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.create_task("Retry ceiling", "Do not exceed policy attempts", [])
    first = storage.claim_task_with_lease(task.id, "worker-a", 5)
    assert first is not None
    future = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
    assert storage.mark_expired_task_attempts(now=future) == 1
    assert storage.resolve_task_recovery(
        task.id, first["attempt_id"], "retry", "operator", "Explicit recovery",
        retry_safe=True, side_effects_reconciled=True,
    )
    second = storage.claim_task_with_lease(task.id, "worker-b", 30)
    assert second is not None and second["attempt_number"] == 2
    schedule = _schedule_retry(task.id, second, max_attempts=2)
    assert schedule is None
    assert manager.get_task(task.id).status == "running"
    assert storage.get_task_attempts(task.id)[-1]["state"] == "active"
