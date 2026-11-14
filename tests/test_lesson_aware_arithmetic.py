import pytest

from atlas_engine.lesson_aware_arithmetic import LessonAwareArithmeticExecutor
from atlas_engine.lesson_contract import validate_lesson_aware_result


def _lesson(alias="double dozen", expression="12 * 2", **extra):
    return {
        "id": "lesson-alias-1",
        "validated": True,
        "lesson_type": "arithmetic_alias",
        "application": {"alias": alias, "expression": expression},
        **extra,
    }


def test_exact_validated_alias_is_applied_and_receipted():
    executor = LessonAwareArithmeticExecutor()
    result = executor.execute({
        "description": "  Double Dozen ",
        "relevant_lessons": [_lesson()],
    })
    checked = validate_lesson_aware_result(result, [_lesson()])
    assert checked.output == {"type": "safe_math", "value": 24}
    assert checked.consumed_lesson_ids == ("lesson-alias-1",)


def test_unvalidated_or_unrelated_lessons_are_not_used():
    executor = LessonAwareArithmeticExecutor()
    lesson = _lesson()
    lesson["validated"] = False
    result = executor.execute({
        "description": "2 + 2",
        "relevant_lessons": [lesson, _lesson(alias="double dozen")],
    })
    assert result.output["value"] == 4
    assert result.consumed_lesson_ids == ()


def test_arbitrary_natural_language_is_not_interpreted():
    executor = LessonAwareArithmeticExecutor()
    with pytest.raises(ValueError, match="not a supported arithmetic"):
        executor.execute({
            "description": "please calculate something clever",
            "relevant_lessons": [],
        })


def test_ambiguous_exact_alias_fails_closed():
    first = _lesson()
    second = {**_lesson(expression="6 * 4"), "id": "lesson-alias-2"}
    executor = LessonAwareArithmeticExecutor()
    with pytest.raises(ValueError, match="ambiguous"):
        executor.execute({
            "description": "double dozen",
            "relevant_lessons": [first, second],
        })


def test_lesson_expression_still_passes_through_safe_math_restrictions():
    executor = LessonAwareArithmeticExecutor()
    malicious = _lesson(expression="__import__('os').system('echo unsafe')")
    with pytest.raises(ValueError, match="basic arithmetic"):
        executor.execute({
            "description": "double dozen",
            "relevant_lessons": [malicious],
        })


def test_non_alias_lesson_types_are_ignored():
    lesson = _lesson()
    lesson["lesson_type"] = "general_advice"
    result = LessonAwareArithmeticExecutor().execute({
        "description": "3 * 3",
        "relevant_lessons": [lesson],
    })
    assert result.output["value"] == 9
    assert result.consumed_lesson_ids == ()
