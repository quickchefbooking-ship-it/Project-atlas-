import json
import sqlite3

import pytest

from atlas_engine import storage
from atlas_engine.lesson_contract import LessonAwareResult
from atlas_engine.lesson_experiment_runner import OfflineLessonExperimentRunner
from atlas_engine.lesson_experiment_store import (
    get_lesson_experiment_run,
    save_lesson_experiment_run,
)


@pytest.fixture
def experiment_db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "experiments.sqlite3"))
    storage.init_db()
    return storage.DB_PATH


def _result(experiment_id="durable-1"):
    cases = [
        {
            "case_id": f"case-{index}",
            "task_input": {"prompt": f"private input {index}"},
            "success_criteria": {"field": "value", "operator": "==", "expected_value": index},
        }
        for index in range(10)
    ]
    runner = OfflineLessonExperimentRunner(
        lambda payload: {"value": int(payload["case_id"].split("-")[1]), "private": "raw output"},
        lambda payload: LessonAwareResult(
            {"value": int(payload["case_id"].split("-")[1]), "private": "raw output"},
            ("lesson-1",),
        ),
    )
    return runner.run(
        cases, experiment_id=experiment_id, criteria_version="criteria-v1",
        validated_lessons=[{"id": "lesson-1", "validated": True, "summary": "private lesson text"}],
        seed=23,
    )


def test_runner_does_not_persist_by_default(experiment_db):
    result = _result()
    assert "stored_record" not in result
    assert get_lesson_experiment_run("durable-1") is None


def test_explicit_persistence_round_trips_minimised_integrity_checked_record(experiment_db):
    result = _result()
    stored = save_lesson_experiment_run(result)
    loaded = get_lesson_experiment_run("durable-1")

    assert loaded["report"] == result["report"]
    assert loaded["observations"] == result["observations"]
    assert loaded["arm_order_seed"] == 23
    assert loaded["payload_sha256"] == stored["payload_sha256"]
    encoded = json.dumps(loaded)
    assert "private input" not in encoded
    assert "raw output" not in encoded
    assert "private lesson text" not in encoded
    assert loaded["evidence"][0]["arms"]["lesson_enabled"]["consumed_lesson_ids"] == ["lesson-1"]


def test_runner_persists_only_when_explicitly_requested(experiment_db):
    result = _result("runner-persist")
    assert get_lesson_experiment_run("runner-persist") is None
    # Re-run through a fresh runner with the explicit opt-in flag.
    runner = OfflineLessonExperimentRunner(
        lambda payload: {"value": int(payload["case_id"].split("-")[1])},
        lambda payload: LessonAwareResult({"value": int(payload["case_id"].split("-")[1])}, ()),
    )
    cases = [
        {"case_id": f"case-{i}", "task_input": {}, "success_criteria": {
            "field": "value", "operator": "==", "expected_value": i
        }} for i in range(10)
    ]
    persisted = runner.run(
        cases, experiment_id="runner-persist", criteria_version="v1",
        validated_lessons=[], persist=True,
    )
    assert persisted["stored_record"]["experiment_id"] == "runner-persist"
    assert get_lesson_experiment_run("runner-persist") is not None


def test_duplicate_experiment_id_is_rejected_without_overwriting(experiment_db):
    first = _result()
    save_lesson_experiment_run(first)
    with pytest.raises(ValueError, match="already exists"):
        save_lesson_experiment_run(_result())
    assert get_lesson_experiment_run("durable-1")["report"] == first["report"]


def test_non_finite_or_non_json_data_is_rejected(experiment_db):
    result = _result()
    result["evidence"][0]["arms"]["baseline"]["score"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        save_lesson_experiment_run(result)


def test_record_integrity_is_checked_on_read(experiment_db):
    save_lesson_experiment_run(_result())
    conn = sqlite3.connect(experiment_db)
    try:
        conn.execute(
            "UPDATE lesson_experiment_runs SET payload_json = ? WHERE experiment_id = ?",
            ('{"tampered":true}', "durable-1"),
        )
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ValueError, match="integrity"):
        get_lesson_experiment_run("durable-1")


def test_executor_failure_does_not_create_a_durable_run(experiment_db):
    runner = OfflineLessonExperimentRunner(
        lambda _payload: (_ for _ in ()).throw(RuntimeError("failed")),
        lambda _payload: LessonAwareResult({"value": 0}, ()),
    )
    cases = [{"case_id": "one", "task_input": {}, "success_criteria": {"field": "value"}}]
    with pytest.raises(RuntimeError, match="failed"):
        runner.run(
            cases, experiment_id="failed-run", criteria_version="v1",
            validated_lessons=[], persist=True,
        )
    assert get_lesson_experiment_run("failed-run") is None
