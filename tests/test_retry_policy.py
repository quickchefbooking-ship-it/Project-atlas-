import pytest

from atlas_engine.retry_policy import (
    CapabilityRetryContract,
    RetryPolicy,
    RetryableExecutionError,
    TerminalExecutionError,
    evaluate_retry,
)


def _safe_contract():
    return CapabilityRetryContract(
        capability_name="test.read",
        version="1",
        idempotent=True,
        side_effects_declared=True,
        duplicate_suppression_verified=True,
        retryable_error_codes=frozenset({"temporary_unavailable"}),
    )


def test_default_policy_preserves_single_attempt_compatibility():
    decision = evaluate_retry(
        RetryableExecutionError("temporary_unavailable"),
        attempt_number=1,
        policy=RetryPolicy(),
        capability=_safe_contract(),
        elapsed_seconds=0,
    )
    assert not decision.eligible
    assert decision.reason == "automatic_retry_disabled"


def test_only_explicit_retryable_error_with_proven_contract_is_eligible():
    decision = evaluate_retry(
        RetryableExecutionError("temporary_unavailable"),
        attempt_number=1,
        policy=RetryPolicy(max_attempts=3),
        capability=_safe_contract(),
        elapsed_seconds=0,
        jitter_fraction=0.5,
    )
    assert decision.eligible
    assert decision.retry_after_seconds == 0.5


@pytest.mark.parametrize(
    "error",
    [
        ValueError("invalid input"),
        PermissionError("denied"),
        TerminalExecutionError("policy blocked"),
        RuntimeError("unknown failure"),
    ],
)
def test_unknown_validation_permission_and_terminal_errors_never_retry(error):
    decision = evaluate_retry(
        error,
        attempt_number=1,
        policy=RetryPolicy(max_attempts=3),
        capability=_safe_contract(),
        elapsed_seconds=0,
    )
    assert not decision.eligible
    assert decision.reason == "error_not_explicitly_retryable"


def test_retryable_error_code_must_be_allowlisted():
    decision = evaluate_retry(
        RetryableExecutionError("not_allowlisted"),
        attempt_number=1,
        policy=RetryPolicy(max_attempts=3),
        capability=_safe_contract(),
        elapsed_seconds=0,
    )
    assert not decision.eligible
    assert decision.reason == "error_code_not_allowlisted"


@pytest.mark.parametrize(
    "contract",
    [
        None,
        CapabilityRetryContract("x", "1"),
        CapabilityRetryContract("x", "1", idempotent=True),
        CapabilityRetryContract(
            "x", "1", idempotent=True, side_effects_declared=True,
            duplicate_suppression_verified=False,
            retryable_error_codes=frozenset({"temporary_unavailable"}),
        ),
    ],
)
def test_retry_requires_complete_capability_idempotency_contract(contract):
    decision = evaluate_retry(
        RetryableExecutionError("temporary_unavailable"),
        attempt_number=1,
        policy=RetryPolicy(max_attempts=3),
        capability=contract,
        elapsed_seconds=0,
    )
    assert not decision.eligible
    assert decision.reason == "capability_not_proven_idempotent"


def test_attempt_ceiling_includes_initial_attempt():
    decision = evaluate_retry(
        RetryableExecutionError("temporary_unavailable"),
        attempt_number=3,
        policy=RetryPolicy(max_attempts=3),
        capability=_safe_contract(),
        elapsed_seconds=0,
    )
    assert not decision.eligible
    assert decision.reason == "maximum_attempts_reached"


def test_cancellation_lease_uncertainty_and_persistence_failure_block_retry():
    error = RetryableExecutionError("temporary_unavailable")
    common = dict(
        error=error,
        attempt_number=1,
        policy=RetryPolicy(max_attempts=3),
        capability=_safe_contract(),
        elapsed_seconds=0,
    )
    assert evaluate_retry(**common, cancellation_requested=True).reason == "cancellation_requested"
    assert evaluate_retry(**common, lease_uncertain=True).reason == "lease_outcome_uncertain"
    assert evaluate_retry(**common, persistence_failed=True).reason == "persistence_failure"


def test_backoff_is_exponential_capped_and_jitter_bounded():
    policy = RetryPolicy(max_attempts=3, base_delay_seconds=2, max_delay_seconds=3)
    first = evaluate_retry(
        RetryableExecutionError("temporary_unavailable"),
        attempt_number=1, policy=policy, capability=_safe_contract(),
        elapsed_seconds=0, jitter_fraction=0.25,
    )
    second = evaluate_retry(
        RetryableExecutionError("temporary_unavailable"),
        attempt_number=2, policy=policy, capability=_safe_contract(),
        elapsed_seconds=0, jitter_fraction=1,
    )
    assert first.retry_after_seconds == 0.5
    assert second.retry_after_seconds == 3


def test_retry_is_refused_when_delay_would_exceed_total_deadline():
    decision = evaluate_retry(
        RetryableExecutionError("temporary_unavailable"),
        attempt_number=1,
        policy=RetryPolicy(max_attempts=3, total_deadline_seconds=2),
        capability=_safe_contract(),
        elapsed_seconds=1.5,
        jitter_fraction=1,
    )
    assert not decision.eligible
    assert decision.reason == "retry_would_exceed_task_deadline"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_attempts": 0},
        {"max_attempts": 4},
        {"per_attempt_timeout_seconds": 31},
        {"total_deadline_seconds": 91},
        {"base_delay_seconds": 16},
        {"max_delay_seconds": 16},
        {"base_delay_seconds": 2, "max_delay_seconds": 1},
    ],
)
def test_server_side_retry_policy_caps_are_validated(kwargs):
    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)


def test_retry_evaluator_rejects_invalid_inputs():
    args = dict(
        error=RetryableExecutionError("temporary_unavailable"),
        policy=RetryPolicy(max_attempts=3),
        capability=_safe_contract(),
        elapsed_seconds=0,
    )
    with pytest.raises(ValueError):
        evaluate_retry(**args, attempt_number=0)
    with pytest.raises(ValueError):
        evaluate_retry(**args, attempt_number=1, jitter_fraction=1.1)
    with pytest.raises(ValueError):
        evaluate_retry(**{**args, "elapsed_seconds": -1}, attempt_number=1)
