from atlas_engine.billing_readiness import (
    MAX_EVIDENCE_REFERENCE_CHARS,
    REQUIRED_LIVE_READINESS_GATES,
    evaluate_live_billing_readiness,
)


def complete_evidence():
    return {
        gate: {"passed": True, "reference": f"review-record-{index + 1}"}
        for index, gate in enumerate(REQUIRED_LIVE_READINESS_GATES)
    }


def test_billing_preflight_fails_closed_when_no_evidence_is_available():
    report = evaluate_live_billing_readiness(None)
    assert report["overall_status"] == "blocked"
    assert report["required_gate_count"] == len(REQUIRED_LIVE_READINESS_GATES)
    assert report["passed_gate_count"] == 0
    assert report["blocked_gates"] == list(REQUIRED_LIVE_READINESS_GATES)
    assert report["live_release_approval"] == "not_requested"
    assert report["live_charging_enabled"] is False


def test_billing_preflight_passes_only_when_every_gate_has_referenced_evidence():
    report = evaluate_live_billing_readiness(complete_evidence())
    assert report["overall_status"] == "ready_for_human_release_review"
    assert report["passed_gate_count"] == len(REQUIRED_LIVE_READINESS_GATES)
    assert report["blocked_gates"] == []
    assert report["live_release_approval"] == "not_requested"
    assert report["live_charging_enabled"] is False


def test_billing_preflight_blocks_missing_false_and_unreferenced_evidence():
    evidence = complete_evidence()
    evidence["provider_selected"] = {"passed": True, "reference": ""}
    evidence["test_checkout_completed"] = {"passed": False, "reference": "test-run-22"}
    del evidence["webhook_signature_verification_passed"]
    report = evaluate_live_billing_readiness(evidence)
    assert report["overall_status"] == "blocked"
    assert {
        "provider_selected",
        "test_checkout_completed",
        "webhook_signature_verification_passed",
    }.issubset(set(report["blocked_gates"]))


def test_billing_preflight_rejects_truthy_non_boolean_and_oversized_evidence():
    evidence = complete_evidence()
    evidence["provider_selected"] = {"passed": "true", "reference": "review-1"}
    evidence["dedicated_atlas_account_verified"] = {
        "passed": True, "reference": "x" * 257,
    }
    report = evaluate_live_billing_readiness(evidence)
    assert "provider_selected" in report["blocked_gates"]
    assert "dedicated_atlas_account_verified" in report["blocked_gates"]


def test_billing_preflight_rejects_raw_oversized_reference_even_when_trimmed_value_is_short():
    evidence = complete_evidence()
    evidence["provider_selected"] = {
        "passed": True,
        "reference": (" " * (MAX_EVIDENCE_REFERENCE_CHARS + 1)) + "x",
    }

    report = evaluate_live_billing_readiness(evidence)

    assert report["overall_status"] == "blocked"
    assert "provider_selected" in report["blocked_gates"]
    assert report["live_charging_enabled"] is False


def test_billing_preflight_report_never_echoes_secret_or_evidence_values():
    secret = "sk_live_DO_NOT_DISCLOSE_123"
    evidence = complete_evidence()
    evidence["provider_selected"] = {"passed": True, "reference": secret}
    report = evaluate_live_billing_readiness(evidence)
    rendered = repr(report)
    assert secret not in rendered
    assert "review-record-1" not in rendered
    assert report["live_charging_enabled"] is False


def test_unknown_evidence_keys_do_not_change_required_gate_set():
    evidence = complete_evidence()
    evidence["owner_says_go_live"] = {"passed": True, "reference": "chat-message"}
    report = evaluate_live_billing_readiness(evidence)
    assert report["overall_status"] == "ready_for_human_release_review"
    assert report["live_charging_enabled"] is False
