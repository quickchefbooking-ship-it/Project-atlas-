import pytest

from atlas_engine import storage
from atlas_engine.learning_memory import LearningMemory


def _isolated_db(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "learning-memory.db"))
    storage.init_db()
    now = storage.now_isoformat()
    storage.save_task({
        "id": "task-learning-test",
        "title": "Learning memory test",
        "description": "Verify lesson review boundaries.",
        "success_criteria_json": "[]",
        "status": "passed",
        "attempts": 1,
        "score": 1.0,
        "result_json": "{}",
        "created_at": now,
        "updated_at": now,
    })


def test_new_lessons_are_always_unvalidated(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)

    lesson = LearningMemory.save_lesson_for_task(
        "task-learning-test",
        "success",
        "A successful outcome should be reviewed before reuse.",
        "deterministic-evaluation",
        {"evaluation_passed": True},
    )

    assert lesson["validated"] is False
    assert storage.list_lessons(limit=10, validated_only=True) == []
    stored = storage.list_lessons(limit=10)
    assert len(stored) == 1
    assert stored[0]["validated"] == 0


def test_lesson_creator_cannot_self_validate(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="explicit review is required"):
        LearningMemory.save_lesson_for_task(
            "task-learning-test",
            "success",
            "Do not self-certify this lesson.",
            "deterministic-evaluation",
            {"evaluation_passed": True},
            validated=True,
        )

    assert storage.list_lessons(limit=10) == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"task_id": "", "lesson_type": "success", "summary": "A summary", "source": "test", "evidence": {}},
        {"task_id": "task-learning-test", "lesson_type": "", "summary": "A summary", "source": "test", "evidence": {}},
        {"task_id": "task-learning-test", "lesson_type": "success", "summary": "", "source": "test", "evidence": {}},
        {"task_id": "task-learning-test", "lesson_type": "success", "summary": "A summary", "source": "test", "evidence": []},
    ],
)
def test_lesson_input_validation(monkeypatch, tmp_path, kwargs):
    _isolated_db(monkeypatch, tmp_path)

    with pytest.raises(ValueError):
        LearningMemory.save_lesson_for_task(**kwargs)


def test_relevant_lesson_limit_is_bounded():
    with pytest.raises(ValueError, match="between 1 and 50"):
        LearningMemory.get_relevant_lessons("orchestration", limit=51)
