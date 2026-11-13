"""Fail-closed retry policy primitives for AtlasOnePro.

This module evaluates eligibility only. It does not schedule, sleep, retry, or
execute work. Legacy capabilities remain single-attempt unless explicitly
registered with a verified idempotency contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet


class TerminalExecutionError(Exception):
    """An execution failure that must never be automatically retried."""


class RetryableExecutionError(Exception):
    """A narrowly classified transient failure from an opted-in capability."""

    def __init__(self, error_code: str, message: str = "Transient execution failure"):
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True)
class RetryPolicy:
    """Immutable server-side retry limits; max_attempts includes the first run."""

    max_attempts: int = 1
    per_attempt_timeout_seconds: int = 30
    total_deadline_seconds: int = 90
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 15.0

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")
        if not 1 <= self.per_attempt_timeout_seconds <= 30:
            raise ValueError("per-attempt timeout must be between 1 and 30 seconds")
        if not 1 <= self.total_deadline_seconds <= 90:
            raise ValueError("total deadline must be between 1 and 90 seconds")
        if not 0 < self.base_delay_seconds <= 15:
            raise ValueError("base delay must be greater than 0 and at most 15 seconds")
        if not 0 < self.max_delay_seconds <= 15:
            raise ValueError("maximum delay must be greater than 0 and at most 15 seconds")
        if self.base_delay_seconds > self.max_delay_seconds:
            raise ValueError("base delay cannot exceed maximum delay")


@dataclass(frozen=True)
class CapabilityRetryContract:
    """Retry declaration supplied by trusted application code, never task input."""

    capability_name: str
    version: str
    idempotent: bool = False
    side_effects_declared: bool = False
    duplicate_suppression_verified: bool = False
    retryable_error_codes: FrozenSet[str] = frozenset()

    @property
    def retry_is_safe(self) -> bool:
        return bool(
            self.capability_name.strip()
            and self.version.strip()
            and self.idempotent
            and self.side_effects_declared
            and self.duplicate_suppression_verified
            and self.retryable_error_codes
        )


@dataclass(frozen=True)
class RetryDecision:
    eligible: bool
    reason: str
    retry_after_seconds: float | None = None


def evaluate_retry(
    error: BaseException,
    *,
    attempt_number: int,
    policy: RetryPolicy,
    capability: CapabilityRetryContract | None,
    elapsed_seconds: float,
    jitter_fraction: float = 0.5,
    cancellation_requested: bool = False,
    lease_uncertain: bool = False,
    persistence_failed: bool = False,
) -> RetryDecision:
    """Return a bounded retry decision without performing or scheduling a retry.

    Unknown errors fail closed. jitter_fraction is an injected value in [0, 1]
    so tests and a future scheduler can control randomness without sleeping.
    """
    if attempt_number < 1:
        raise ValueError("attempt_number must be at least 1")
    if elapsed_seconds < 0:
        raise ValueError("elapsed_seconds cannot be negative")
    if not 0 <= jitter_fraction <= 1:
        raise ValueError("jitter_fraction must be between 0 and 1")

    if persistence_failed:
        return RetryDecision(False, "persistence_failure")
    if lease_uncertain:
        return RetryDecision(False, "lease_outcome_uncertain")
    if cancellation_requested:
        return RetryDecision(False, "cancellation_requested")
    if not isinstance(error, RetryableExecutionError):
        return RetryDecision(False, "error_not_explicitly_retryable")
    if capability is None or not capability.retry_is_safe:
        return RetryDecision(False, "capability_not_proven_idempotent")
    if error.error_code not in capability.retryable_error_codes:
        return RetryDecision(False, "error_code_not_allowlisted")
    if policy.max_attempts <= 1:
        return RetryDecision(False, "automatic_retry_disabled")
    if attempt_number >= policy.max_attempts:
        return RetryDecision(False, "maximum_attempts_reached")
    if elapsed_seconds >= policy.total_deadline_seconds:
        return RetryDecision(False, "task_deadline_reached")

    exponential = policy.base_delay_seconds * (2 ** (attempt_number - 1))
    capped_delay = min(exponential, policy.max_delay_seconds)
    delay = capped_delay * jitter_fraction
    if elapsed_seconds + delay >= policy.total_deadline_seconds:
        return RetryDecision(False, "retry_would_exceed_task_deadline")
    return RetryDecision(True, "explicit_transient_error_and_idempotency_proven", delay)
