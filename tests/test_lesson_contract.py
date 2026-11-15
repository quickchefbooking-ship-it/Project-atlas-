import pytest

from atlas_engine.lesson_contract import (
    LessonAwareResult,
    MAX_CONSUMED_LESSON_IDS,
    validate_lesson_aware_result,
)


def _lessons():
    return [
        {"id": "lesson-approved", "validated": 1, "summary": "reviewed"},
        {"id": "lesson-boolean", "validated": True, "summary": "reviewed"},
        {"id": "lesson-unreviewed", "validated": 0, "summary": "not trusted"},
        {"id": "lesson-string-flag", "validated": "true", "summary": "not trusted"},
    ]


def test_receipt_accepts_only_ids_from_validated_supplied_context():
    result = LessonAwareResult(
        output={"answer": 42},
        consumed_lesson_ids=("lesson-approved", "lesson-boolean"),
    )
    checked = validate_lesson_aware_result(result, _lessons())
    assert checked is result
    assert checked.output == {"answer": 42}


@pytest.mark.parametrize("lesson_id", [
    "lesson-unreviewed",
    "lesson-string-flag",
    "lesson-never-supplied",
])
def test_receipt_rejects_unvalidated_or_unsupplied_lesson_ids(lesson_id):
    result = LessonAwareResult(output={"answer": 42}, consumed_lesson_ids=(lesson_id,))
    with pytest.raises(ValueError, match="outside validated supplied context"):
        validate_lesson_aware_result(result, _lessons())


def test_receipt_rejects_plain_dict_result_without_explicit_contract():
    with pytest.raises(ValueError, match="LessonAwareResult"):
        validate_lesson_aware_result(
            {"output": {"answer": 42}, "consumed_lesson_ids": ["lesson-approved"]},
            _lessons(),
        )


def test_receipt_is_immutable_and_rejects_mutable_id_list():
    with pytest.raises(ValueError, match="immutable tuple"):
        LessonAwareResult(output={"answer": 42}, consumed_lesson_ids=["lesson-approved"])
    result = LessonAwareResult(output={"answer": 42}, consumed_lesson_ids=("lesson-approved",))
    with pytest.raises((AttributeError, TypeError)):
        result.consumed_lesson_ids = ()


def test_receipt_rejects_duplicate_ids_and_oversized_receipts():
    with pytest.raises(ValueError, match="unique"):
        LessonAwareResult(output={}, consumed_lesson_ids=("lesson-approved", "lesson-approved"))
    with pytest.raises(ValueError, match="supported limit"):
        LessonAwareResult(
            output={},
            consumed_lesson_ids=tuple(f"lesson-{index}" for index in range(MAX_CONSUMED_LESSON_IDS + 1)),
        )


@pytest.mark.parametrize("lesson_id", ["", " ", 42, None])
def test_receipt_rejects_invalid_ids(lesson_id):
    with pytest.raises(ValueError, match="bounded string"):
        LessonAwareResult(output={}, consumed_lesson_ids=(lesson_id,))


def test_receipt_rejects_non_list_context():
    result = LessonAwareResult(output={}, consumed_lesson_ids=())
    with pytest.raises(ValueError, match="must be a list"):
        validate_lesson_aware_result(result, ())
