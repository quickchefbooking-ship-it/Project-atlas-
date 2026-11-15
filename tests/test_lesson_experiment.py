import pytest

from atlas_engine.lesson_experiment import analyse_paired_lesson_experiment


def _rows(count=10, *, baseline=False, treatment=True):
    rows = []
    for index in range(count):
        rows.extend([
            {
                "case_id": f"case-{index}",
                "arm": "baseline",
                "passed": baseline,
                "criteria_version": "criteria-v1",
            },
            {
                "case_id": f"case-{index}",
                "arm": "lesson_enabled",
                "passed": treatment,
                "criteria_version": "criteria-v1",
            },
        ])
    return rows


def test_paired_experiment_reports_descriptive_positive_signal_only():
    report = analyse_paired_lesson_experiment(
        _rows(), experiment_id="pilot-1", criteria_version="criteria-v1"
    )

    assert report["status"] == "descriptive_positive_signal"
    assert report["pairs"] == 10
    assert report["baseline"]["pass_rate"] == 0.0
    assert report["lesson_enabled"]["pass_rate"] == 1.0
    assert report["paired_outcomes"] == {"improved": 10, "regressed": 0, "unchanged": 0}
    assert "does not establish causality" in report["interpretation"]


def test_small_sample_is_insufficient_even_with_large_difference():
    report = analyse_paired_lesson_experiment(
        _rows(2), experiment_id="pilot-small", criteria_version="criteria-v1"
    )
    assert report["status"] == "insufficient_data"


def test_equal_outcomes_are_reported_as_no_difference():
    report = analyse_paired_lesson_experiment(
        _rows(baseline=True, treatment=True),
        experiment_id="pilot-equal",
        criteria_version="criteria-v1",
    )
    assert report["status"] == "no_descriptive_difference"
    assert report["absolute_pass_rate_difference"] == 0.0


@pytest.mark.parametrize("rows, message", [
    (_rows()[:-1], "both baseline"),
    (_rows() + [_rows()[0]], "exactly one"),
    ([{**_rows()[0], "criteria_version": "criteria-v2"}, _rows()[1]], "criteria version"),
    ([{**_rows()[0], "passed": 1}, _rows()[1]], "must be a boolean"),
    ([{**_rows()[0], "arm": "unknown"}, _rows()[1]], "arm must be"),
])
def test_invalid_or_unpaired_observations_are_rejected(rows, message):
    with pytest.raises(ValueError, match=message):
        analyse_paired_lesson_experiment(
            rows, experiment_id="pilot-invalid", criteria_version="criteria-v1"
        )


def test_duplicate_case_ids_are_not_silently_aggregated():
    rows = _rows(1) + _rows(1)
    with pytest.raises(ValueError, match="exactly one"):
        analyse_paired_lesson_experiment(
            rows, experiment_id="pilot-duplicate", criteria_version="criteria-v1"
        )


def test_empty_observation_set_is_rejected():
    with pytest.raises(ValueError, match="At least one"):
        analyse_paired_lesson_experiment(
            [], experiment_id="pilot-empty", criteria_version="criteria-v1"
        )
