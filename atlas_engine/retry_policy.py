"""Fail-closed retry policy primitives for AtlasOnePro.

This module evaluates eligibility only. It does not schedule, sleep, retry, or
execute work. Legacy capabilities remain single-attempt unless explicitly
registered with a verified idempotency contract.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import FrozenSet


class TerminalExecutionError(Exception):
    """An execution failure that must never be automatically retried."""


_ERROR_CODE_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")


class RetryableExecutionError(Exception):
    """A narrowly classified transient failure from an opted-in capability."""

    def __init__(self, error_code: str, message: str = "Transient execution failure"):
        if not isinstance(error_code, str) or not _ERROR_CODE_PATTERN.fullmatch(error_code):
            raise ValueError("error_code must be a 1-64 character identifier")
        if not isinstance(message, str):
            raise ValueError("message must be a string")
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
        for name, value in (("max_attempts", self.max_attempts), ("per_attempt_timeout_seconds", self.per_attempt_timeout_seconds), ("total_deadline_seconds", self.total_deadline_seconds)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
        for name, value in (("base_delay_seconds", self.base_delay_seconds), ("max_delay_seconds", self.max_delay_seconds)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
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
    verification_evidence: str = ""
    retryable_error_codes: FrozenSet[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.capability_name, str) or not self.capability_name.strip():
            raise ValueError("capability_name is required")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("capability version is required")
        for name, value in (
            ("idempotent", self.idempotent),
            ("side_effects_declared", self.side_effects_declared),
            ("duplicate_suppression_verified", self.duplicate_suppression_verified),
        ):
            if type(value) is not bool:
                raise ValueError(f"{name} must be a boolean")
        if not isinstance(self.verification_evidence, str) or len(self.verification_evidence) > 512:
            raise ValueError("verification evidence reference must be a string of at most 512 characters")
        if not isinstance(self.retryable_error_codes, (set, frozenset)) or any(
            not isinstance(code, str) or not _ERROR_CODE_PATTERN.fullmatch(code)
            for code in self.retryable_error_codes
        ):
            raise ValueError("retryable error codes must be valid 1-64 character identifiers")
        # A frozen dataclass does not freeze a mutable set supplied by its caller.
        # Copy to a frozenset so the allowlist cannot change after validation.
        object.__setattr__(self, "capability_name", self.capability_name.strip())
        object.__setattr__(self, "version", self.version.strip())
        object.__setattr__(self, "retryable_error_codes", frozenset(self.retryable_error_codes))

    @property
    def retry_is_safe(self) -> bool:
        return bool(
            self.capability_name
            and self.version
            and self.idempotent is True
            and self.side_effects_declared is True
            and self.duplicate_suppression_verified is True
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
    if isinstance(attempt_number, bool) or not isinstance(attempt_number, int) or attempt_number < 1:
        raise ValueError("attempt_number must be a positive integer")
    if not isinstance(policy, RetryPolicy):
        raise ValueError("policy must be a validated RetryPolicy")
    if isinstance(elapsed_seconds, bool) or not isinstance(elapsed_seconds, (int, float)) or not math.isfinite(elapsed_seconds) or elapsed_seconds < 0:
        raise ValueError("elapsed_seconds must be a finite non-negative number")
    if isinstance(jitter_fraction, bool) or not isinstance(jitter_fraction, (int, float)) or not math.isfinite(jitter_fraction) or not 0 <= jitter_fraction <= 1:
        raise ValueError("jitter_fraction must be between 0 and 1")

    if persistence_failed:
        return RetryDecision(False, "persistence_failure")
    if lease_uncertain:
        return RetryDecision(False, "lease_outcome_uncertain")
    if cancellation_requested:
        return RetryDecision(False, "cancellation_requested")
    if not isinstance(error, RetryableExecutionError):
        return RetryDecision(False, "error_not_explicitly_retryable")
    if not isinstance(capability, CapabilityRetryContract) or not capability.retry_is_safe:
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
