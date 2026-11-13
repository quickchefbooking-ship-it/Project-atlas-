import json

import pytest

from atlas_engine import storage


def _isolated_db(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "learning-overview.db"))
    storage.init_db()


def _save_task(task_id, status="passed"):
    now = storage.now_isoformat()
    storage.save_task({
        "id": task_id,
        "title": "Private title must not appear in overview",
        "description": "Private description must not appear in overview",
        "success_criteria_json": "[]",
        "status": status,
        "attempts": 1,
        "score": 1.0 if status == "passed" else 0.0,
        "result_json": json.dumps({"private_result": "must not be exposed"}),
        "created_at": now,
        "updated_at": now,
    })


def _save_evaluation(task_id, passed, method="deterministic", score=1.0):
    conn = storage.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO evaluations (
                id, task_id, passed, score, reasons_json,
                missing_requirements_json, method, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"evaluation-{task_id}-{method}",
                task_id,
                int(passed),
                score,
                "[]",
                "[]",
                method,
                storage.now_isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_learning_overview_empty_database_is_honest(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)

    overview = storage.get_learning_overview()

    assert overview["tasks"] == {"total": 0, "by_status": {}}
    assert overview["evaluations"]["total"] == 0
    assert overview["evaluations"]["deterministic_pass_rate"]["value"] is None
    assert overview["evaluations"]["deterministic_pass_rate"]["status"] == "not_measured"
    assert overview["lessons"]["by_review_state"] == {"unvalidated": 0, "validated": 0}
    assert overview["improvement"]["status"] == "not_measured"
    assert overview["recent_lessons"] == []
    assert overview["recent_evaluations"] == []


def test_learning_overview_aggregates_real_records_and_limits_private_fields(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    _save_task("task-one", "passed")
    _save_task("task-two", "failed")
    _save_evaluation("task-one", True)
    _save_evaluation("task-two", False)
    _save_evaluation("task-two", False, method="execution_error", score=0.0)

    storage.save_lesson({
        "id": "lesson-pending",
        "task_id": "task-two",
        "lesson_type": "execution_failure",
        "summary": "Review the sanitised failure evidence.",
        "source": "execution-error",
        "evidence_json": json.dumps({"private": "do not expose"}),
        "validated": False,
        "created_at": storage.now_isoformat(),
    })
    storage.save_lesson({
        "id": "lesson-reviewed",
        "task_id": "task-one",
        "lesson_type": "reviewed",
        "summary": "A reviewed lesson summary.",
        "source": "human-review",
        "evidence_json": "{}",
        "validated": True,
        "created_at": storage.now_isoformat(),
    })

    overview = storage.get_learning_overview()

    assert overview["tasks"]["total"] == 2
    assert overview["tasks"]["by_status"] == {"failed": 1, "passed": 1}
    assert overview["evaluations"]["total"] == 3
    rate = overview["evaluations"]["deterministic_pass_rate"]
    assert rate["numerator"] == 1
    assert rate["denominator"] == 2
    assert rate["value"] == 0.5
    assert overview["evaluations"]["by_method"]["execution_error"]["total"] == 1
    assert overview["lessons"]["by_review_state"] == {"unvalidated": 1, "validated": 1}
    assert overview["lessons"]["reviewer_identity_verified"] is False
    assert overview["improvement"]["status"] == "not_measured"
    assert len(overview["recent_lessons"]) == 2
    assert all("evidence_json" not in item for item in overview["recent_lessons"])
    assert all("description" not in item and "result_json" not in item for item in overview["recent_evaluations"])
    assert "private" not in json.dumps(overview)


@pytest.mark.parametrize("limit", [0, 51, -1, True])
def test_learning_overview_rejects_invalid_recent_limits(monkeypatch, tmp_path, limit):
    _isolated_db(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        storage.get_learning_overview(recent_limit=limit)
