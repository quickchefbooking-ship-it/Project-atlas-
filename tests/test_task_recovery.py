from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

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
