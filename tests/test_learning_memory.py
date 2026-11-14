import pytest

from atlas_engine import storage
from atlas_engine.learning_memory import LearningMemory, MAX_LESSON_EVIDENCE_DEPTH


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


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_lesson_evidence_rejects_non_finite_numbers(monkeypatch, tmp_path, value):
    _isolated_db(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="non-finite number"):
        LearningMemory.save_lesson_for_task(
            "task-learning-test",
            "diagnostic",
            "Reject non-standard numeric values in evidence.",
            "test",
            {"nested": {"measurement": value}},
        )

    assert storage.list_lessons(limit=10) == []


def test_lesson_evidence_accepts_finite_nested_json(monkeypatch, tmp_path):
    import json

    _isolated_db(monkeypatch, tmp_path)
    lesson = LearningMemory.save_lesson_for_task(
        "task-learning-test",
        "diagnostic",
        "Persist finite nested evidence.",
        "test",
        {"nested": {"measurement": 1.25}, "labels": ["safe", "finite"]},
    )

    assert json.loads(lesson["evidence_json"]) == {
        "nested": {"measurement": 1.25},
        "labels": ["safe", "finite"],
    }


def test_relevant_lesson_limit_is_bounded():
    with pytest.raises(ValueError, match="between 1 and 50"):
        LearningMemory.get_relevant_lessons("orchestration", limit=51)



def test_retrieval_finds_older_validated_lessons_beyond_recent_hundred(monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone

    _isolated_db(monkeypatch, tmp_path)
    old_id = "lesson-older-relevant"
    storage.save_lesson({
        "id": old_id,
        "task_id": "task-learning-test",
        "lesson_type": "reviewed",
        "summary": "quasar memory recovery guidance",
        "source": "human-reviewed",
        "evidence_json": "{}",
        "validated": True,
        "created_at": "2020-01-01T00:00:00+00:00",
    })

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(105):
        storage.save_lesson({
            "id": f"lesson-new-unrelated-{index:03d}",
            "task_id": "task-learning-test",
            "lesson_type": "reviewed",
            "summary": f"unrelated routine note {index}",
            "source": "human-reviewed",
            "evidence_json": "{}",
            "validated": True,
            "created_at": (base + timedelta(seconds=index)).isoformat(),
        })

    recent_only = storage.list_lessons(limit=100, validated_only=True)
    assert old_id not in {row["id"] for row in recent_only}

    relevant = LearningMemory.get_relevant_lessons("quasar memory recovery", limit=5)

    assert relevant
    assert relevant[0]["id"] == old_id
    assert all(row["validated"] in (1, True) for row in relevant)


def test_retrieval_uses_exact_tokens_not_substrings(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    storage.save_lesson({
        "id": "lesson-word-boundary",
        "task_id": "task-learning-test",
        "lesson_type": "reviewed",
        "summary": "cartography and artifacts",
        "source": "human-reviewed",
        "evidence_json": "{}",
        "validated": True,
        "created_at": storage.now_isoformat(),
    })

    assert LearningMemory.get_relevant_lessons("art", limit=5) == []


@pytest.mark.parametrize("evidence", [
    {1: "non-string key"},
    {"nested": (1, 2)},
    {"nested": {False, True}},
    {"nested": object()},
])
def test_lesson_evidence_rejects_python_only_values(monkeypatch, tmp_path, evidence):
    _isolated_db(monkeypatch, tmp_path)

    with pytest.raises(ValueError):
        LearningMemory.save_lesson_for_task(
            "task-learning-test", "diagnostic", "Reject Python-only values",
            "test", evidence,
        )

    assert storage.list_lessons(limit=10) == []


def test_lesson_evidence_rejects_payload_over_16_kib(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="16,384-byte limit"):
        LearningMemory.save_lesson_for_task(
            "task-learning-test", "diagnostic", "Bound stored evidence",
            "test", {"payload": "x" * 16_385},
        )

    assert storage.list_lessons(limit=10) == []


@pytest.mark.parametrize("container_type", ["list", "dict"])
def test_lesson_evidence_rejects_circular_references(monkeypatch, tmp_path, container_type):
    _isolated_db(monkeypatch, tmp_path)
    cycle = []
    if container_type == "list":
        cycle.append(cycle)
    else:
        cycle.append({"back_reference": cycle})

    with pytest.raises(ValueError, match="circular reference"):
        LearningMemory.save_lesson_for_task(
            "task-learning-test", "diagnostic", "Reject cyclic evidence",
            "test", {"cycle": cycle},
        )

    assert storage.list_lessons(limit=10) == []


def test_lesson_evidence_rejects_excessive_nesting(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    evidence = {}
    current = evidence
    for _ in range(MAX_LESSON_EVIDENCE_DEPTH + 1):
        nested = {}
        current["nested"] = nested
        current = nested

    with pytest.raises(ValueError, match="maximum nesting depth"):
        LearningMemory.save_lesson_for_task(
            "task-learning-test", "diagnostic", "Reject deeply nested evidence",
            "test", evidence,
        )

    assert storage.list_lessons(limit=10) == []



def test_retrieval_decodes_validated_arithmetic_alias_application(monkeypatch, tmp_path):
    import json

    _isolated_db(monkeypatch, tmp_path)
    storage.save_lesson({
        "id": "lesson-arithmetic-alias",
        "task_id": "task-learning-test",
        "lesson_type": "arithmetic_alias",
        "summary": "convert dozen eggs arithmetic alias",
        "source": "reviewed arithmetic rule",
        "evidence_json": json.dumps({
            "application": {"alias": "a dozen eggs", "expression": "12"}
        }),
        "validated": True,
        "created_at": storage.now_isoformat(),
    })

    lessons = LearningMemory.get_relevant_lessons("a dozen eggs", limit=5)

    assert len(lessons) == 1
    assert lessons[0]["validated"] is True
    assert lessons[0]["application"] == {
        "alias": "a dozen eggs",
        "expression": "12",
    }


def test_retrieval_rejects_malformed_validated_arithmetic_alias(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    storage.save_lesson({
        "id": "lesson-arithmetic-alias-invalid",
        "task_id": "task-learning-test",
        "lesson_type": "arithmetic_alias",
        "summary": "convert dozen eggs arithmetic alias",
        "source": "reviewed arithmetic rule",
        "evidence_json": '{"application":{"alias":"a dozen eggs"}}',
        "validated": True,
        "created_at": storage.now_isoformat(),
    })

    with pytest.raises(ValueError, match="application fields"):
        LearningMemory.get_relevant_lessons("a dozen eggs", limit=5)


def test_retrieval_does_not_expose_application_for_other_lesson_types(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    storage.save_lesson({
        "id": "lesson-general",
        "task_id": "task-learning-test",
        "lesson_type": "reviewed",
        "summary": "general dozen eggs handling guidance",
        "source": "human-reviewed",
        "evidence_json": '{"application":{"alias":"a dozen eggs","expression":"12"}}',
        "validated": True,
        "created_at": storage.now_isoformat(),
    })

    lessons = LearningMemory.get_relevant_lessons("dozen eggs", limit=5)

    assert len(lessons) == 1
    assert lessons[0]["validated"] is True
    assert "application" not in lessons[0]
