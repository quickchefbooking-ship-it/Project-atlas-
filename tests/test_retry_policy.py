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
        verification_evidence="tests/test_retry_policy.py::test_fake_provider_deduplicates",
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


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_attempts": True},
        {"max_attempts": 1.5},
        {"per_attempt_timeout_seconds": False},
        {"total_deadline_seconds": float("nan")},
        {"base_delay_seconds": float("inf")},
    ],
)
def test_retry_policy_rejects_non_integer_or_non_finite_values(kwargs):
    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)


def test_retry_evaluator_rejects_non_finite_timing_values():
    args = dict(
        error=RetryableExecutionError("temporary_unavailable"),
        attempt_number=1,
        policy=RetryPolicy(max_attempts=3),
        capability=_safe_contract(),
    )
    with pytest.raises(ValueError):
        evaluate_retry(**args, elapsed_seconds=float("nan"))
    with pytest.raises(ValueError):
        evaluate_retry(**args, elapsed_seconds=0, jitter_fraction=float("inf"))


def test_capability_allowlist_is_frozen_from_mutable_input():
    codes = {"temporary_unavailable"}
    contract = CapabilityRetryContract(
        capability_name="test.read",
        version="1",
        idempotent=True,
        side_effects_declared=True,
        duplicate_suppression_verified=True,
        verification_evidence="tests/test_retry_policy.py::test_fake_provider_deduplicates",
        retryable_error_codes=codes,
    )
    codes.add("permission_denied")
    assert contract.retryable_error_codes == frozenset({"temporary_unavailable"})
    assert isinstance(contract.retryable_error_codes, frozenset)
    decision = evaluate_retry(
        RetryableExecutionError("permission_denied"),
        attempt_number=1,
        policy=RetryPolicy(max_attempts=3),
        capability=contract,
        elapsed_seconds=0,
    )
    assert not decision.eligible
    assert decision.reason == "error_code_not_allowlisted"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"idempotent": "true"},
        {"side_effects_declared": 1},
        {"duplicate_suppression_verified": None},
    ],
)
def test_capability_contract_requires_real_boolean_flags(kwargs):
    with pytest.raises(ValueError, match="must be a boolean"):
        CapabilityRetryContract(
            capability_name="test.read",
            version="1",
            retryable_error_codes=frozenset({"temporary_unavailable"}),
            **kwargs,
        )


@pytest.mark.parametrize("error_code", ["", " ", "not safe!", "x" * 65, [], None])
def test_retryable_error_requires_bounded_identifier(error_code):
    with pytest.raises(ValueError, match="1-64 character identifier"):
        RetryableExecutionError(error_code)


@pytest.mark.parametrize("attempt_number", [True, 1.5, "1", 0, -1])
def test_retry_evaluator_requires_positive_integer_attempt_number(attempt_number):
    with pytest.raises(ValueError, match="positive integer"):
        evaluate_retry(
            RetryableExecutionError("temporary_unavailable"),
            attempt_number=attempt_number,
            policy=RetryPolicy(max_attempts=3),
            capability=_safe_contract(),
            elapsed_seconds=0,
        )


def test_invalid_capability_object_fails_closed():
    decision = evaluate_retry(
        RetryableExecutionError("temporary_unavailable"),
        attempt_number=1,
        policy=RetryPolicy(max_attempts=3),
        capability=object(),
        elapsed_seconds=0,
    )
    assert not decision.eligible
    assert decision.reason == "capability_not_proven_idempotent"


def test_fake_provider_deduplicates_repeated_idempotency_key():
    class FakeProvider:
        def __init__(self):
            self.completed = {}
            self.side_effect_count = 0

        def execute(self, idempotency_key):
            if idempotency_key in self.completed:
                return self.completed[idempotency_key]
            self.side_effect_count += 1
            result = {"receipt": "once"}
            self.completed[idempotency_key] = result
            return result

    provider = FakeProvider()
    first = provider.execute("task-1-attempt-1")
    second = provider.execute("task-1-attempt-1")
    assert first == second
    assert provider.side_effect_count == 1


def test_retry_contract_requires_verification_evidence():
    contract = CapabilityRetryContract(
        capability_name="test.read",
        version="1",
        idempotent=True,
        side_effects_declared=True,
        duplicate_suppression_verified=True,
        retryable_error_codes=frozenset({"temporary_unavailable"}),
    )
    assert not contract.retry_is_safe
