import pytest

from atlas_engine.billing_readiness import (
    REQUIRED_BILLING_GATES,
    evaluate_billing_readiness,
)


def test_empty_checklist_fails_closed_and_lists_every_gate():
    report = evaluate_billing_readiness({})
    assert report.status == "blocked"
    assert report.passed_gates == ()
    assert report.blocked_gates == REQUIRED_BILLING_GATES
    assert report.live_activation_permitted is False


def test_partial_checklist_keeps_missing_gates_blocked():
    report = evaluate_billing_readiness({
        "dedicated_atlas_account": True,
        "test_live_environment_isolation": True,
    })
    assert report.status == "blocked"
    assert report.passed_gates == (
        "dedicated_atlas_account",
        "test_live_environment_isolation",
    )
    assert "independent_security_review" in report.blocked_gates
    assert report.live_activation_permitted is False


def test_all_assertions_only_qualify_for_human_review_not_live_activation():
    report = evaluate_billing_readiness({name: True for name in REQUIRED_BILLING_GATES})
    assert report.status == "eligible_for_human_review"
    assert report.passed_gates == REQUIRED_BILLING_GATES
    assert report.blocked_gates == ()
    assert report.live_activation_permitted is False


def test_unknown_gate_name_is_rejected():
    with pytest.raises(ValueError, match="Unknown"):
        evaluate_billing_readiness({"live_mode_enabled": True})


@pytest.mark.parametrize("value", ["true", 1, None, [], {}])
def test_non_boolean_gate_assertions_are_rejected(value):
    with pytest.raises(TypeError, match="booleans"):
        evaluate_billing_readiness({"dedicated_atlas_account": value})


def test_non_mapping_input_is_rejected():
    with pytest.raises(TypeError, match="mapping"):
        evaluate_billing_readiness([])
