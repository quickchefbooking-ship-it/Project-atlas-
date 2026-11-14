import pytest

from atlas_engine.lesson_contract import LessonAwareResult
from atlas_engine.lesson_experiment_runner import OfflineLessonExperimentRunner


def _cases(count=10):
    return [
        {
            "case_id": f"case-{index}",
            "task_input": {"prompt": f"calculate {index}"},
            "success_criteria": {"field": "value", "operator": "==", "expected_value": index},
        }
        for index in range(count)
    ]


def _lessons():
    return [{"id": "lesson-1", "validated": True, "summary": "Test-only context"}]


def test_runner_executes_matched_arms_with_same_criteria_and_isolated_context():
    baseline_payloads = []
    treatment_payloads = []

    def baseline(payload):
        baseline_payloads.append(payload)
        assert payload["relevant_lessons"] == []
        return {"value": int(payload["case_id"].split("-")[1])}

    def treatment(payload):
        treatment_payloads.append(payload)
        assert payload["relevant_lessons"] == _lessons()
        index = int(payload["case_id"].split("-")[1])
        return LessonAwareResult({"value": index}, ("lesson-1",))

    runner = OfflineLessonExperimentRunner(baseline, treatment)
    report = runner.run(
        _cases(), experiment_id="offline-1", criteria_version="criteria-v1",
        validated_lessons=_lessons(), seed=17,
    )

    assert report["report"]["pairs"] == 10
    assert report["report"]["status"] == "no_descriptive_difference"
    assert len(baseline_payloads) == len(treatment_payloads) == 10
    assert all(item["criteria_version"] == "criteria-v1" for item in baseline_payloads + treatment_payloads)
    assert {item["case_id"] for item in baseline_payloads} == {item["case_id"] for item in treatment_payloads}
    assert all(item["relevant_lessons"] == [] for item in baseline_payloads)
    assert all(item["consumed_lesson_ids"] == ["lesson-1"] for row in report["evidence"] for item in [row["arms"]["lesson_enabled"]])
    assert report["execution_mode"] == "offline_in_process_only"


def test_runner_uses_reproducible_seeded_arm_order():
    def run_order(seed):
        calls = []
        def baseline(payload):
            calls.append((payload["case_id"], "baseline"))
            return {"value": 1}
        def treatment(payload):
            calls.append((payload["case_id"], "lesson_enabled"))
            return LessonAwareResult({"value": 1}, ())
        OfflineLessonExperimentRunner(baseline, treatment).run(
            _cases(4), experiment_id="order", criteria_version="v1",
            validated_lessons=_lessons(), seed=seed,
        )
        return calls

    assert run_order(9) == run_order(9)


def test_baseline_cannot_claim_lesson_use():
    def baseline(_payload):
        return LessonAwareResult({"value": 0}, ("lesson-1",))
    def treatment(_payload):
        return LessonAwareResult({"value": 0}, ())
    runner = OfflineLessonExperimentRunner(baseline, treatment)
    with pytest.raises(ValueError, match="Baseline executor"):
        runner.run(
            _cases(1), experiment_id="bad-baseline", criteria_version="v1",
            validated_lessons=_lessons(),
        )


def test_treatment_cannot_claim_unprovided_or_unvalidated_lesson():
    def baseline(_payload):
        return {"value": 0}
    def treatment(_payload):
        return LessonAwareResult({"value": 0}, ("not-provided",))
    runner = OfflineLessonExperimentRunner(baseline, treatment)
    with pytest.raises(ValueError, match="outside validated supplied context"):
        runner.run(
            _cases(1), experiment_id="bad-receipt", criteria_version="v1",
            validated_lessons=_lessons(),
        )


def test_runner_rejects_unvalidated_context_before_execution():
    called = []
    def executor(_payload):
        called.append(True)
        return {"value": 0}
    runner = OfflineLessonExperimentRunner(executor, executor)
    with pytest.raises(ValueError, match="validated lessons"):
        runner.run(
            _cases(1), experiment_id="bad-context", criteria_version="v1",
            validated_lessons=[{"id": "lesson-bad", "validated": False}],
        )
    assert called == []


def test_executor_failure_aborts_without_returning_partial_report():
    def baseline(_payload):
        raise RuntimeError("offline test executor failed")
    def treatment(_payload):
        return LessonAwareResult({"value": 0}, ())
    runner = OfflineLessonExperimentRunner(baseline, treatment)
    with pytest.raises(RuntimeError, match="offline test executor failed"):
        runner.run(
            _cases(1), experiment_id="failure", criteria_version="v1",
            validated_lessons=_lessons(),
        )


def test_runner_rejects_duplicate_cases_and_invalid_seed():
    runner = OfflineLessonExperimentRunner(lambda _: {"value": 0}, lambda _: LessonAwareResult({"value": 0}, ()))
    with pytest.raises(ValueError, match="unique"):
        runner.run(
            [_cases(1)[0], _cases(1)[0]], experiment_id="duplicate",
            criteria_version="v1", validated_lessons=_lessons(),
        )
    with pytest.raises(ValueError, match="seed"):
        runner.run(
            _cases(1), experiment_id="seed", criteria_version="v1",
            validated_lessons=_lessons(), seed=True,
        )
