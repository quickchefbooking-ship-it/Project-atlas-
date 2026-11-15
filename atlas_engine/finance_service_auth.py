"""Provider-neutral service-principal authorization contract for Finance reads.

This module validates claims supplied by a trusted verifier. It does not parse
or cryptographically verify JWTs, fetch keys, persist replay state, resolve
tenant/account ownership, or perform network requests.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import FrozenSet, Literal, Protocol


FINANCE_PORTFOLIO_READ = "finance:portfolio:read"
ALLOWED_FINANCE_SCOPES = frozenset({FINANCE_PORTFOLIO_READ})
MAX_SUBJECT = 256
MAX_JTI = 256
MAX_SCOPE_COUNT = 16


class ServiceAuthorizationError(ValueError):
    """A service principal is not authorized for the requested capability."""


@dataclass(frozen=True)
class VerifiedServiceTokenClaims:
    """Claims emitted only by a trusted cryptographic token verifier.

    Never construct this object from request JSON or unsigned token contents.
    Account and tenant identifiers are intentionally absent: those mappings
    must be resolved server-side after principal authentication.
    """

    issuer: str
    subject: str
    audience: str
    issued_at: int
    not_before: int
    expires_at: int
    token_id: str
    scopes: tuple[str, ...]
    environment: Literal["demo"]

    def __post_init__(self) -> None:
        if self.environment != "demo":
            raise ServiceAuthorizationError("Only the Demo environment is permitted by this contract.")
        for value, field, limit in (
            (self.issuer, "issuer", 512),
            (self.subject, "subject", MAX_SUBJECT),
            (self.audience, "audience", 512),
            (self.token_id, "token_id", MAX_JTI),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ServiceAuthorizationError(f"{field} must be a non-empty bounded string.")
        for value, field in (
            (self.issued_at, "issued_at"),
            (self.not_before, "not_before"),
            (self.expires_at, "expires_at"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ServiceAuthorizationError(f"{field} must be a positive integer timestamp.")
        if not isinstance(self.scopes, tuple) or not 1 <= len(self.scopes) <= MAX_SCOPE_COUNT:
            raise ServiceAuthorizationError("scopes must be a bounded non-empty tuple.")
        if any(not isinstance(scope, str) or not scope.strip() for scope in self.scopes):
            raise ServiceAuthorizationError("Every scope must be a non-empty string.")
        if len(set(self.scopes)) != len(self.scopes):
            raise ServiceAuthorizationError("Duplicate scopes are not permitted.")
        if not set(self.scopes).issubset(ALLOWED_FINANCE_SCOPES):
            raise ServiceAuthorizationError("The token requests a scope outside the Finance read allowlist.")
        if self.issued_at > self.expires_at or self.not_before > self.expires_at:
            raise ServiceAuthorizationError("Token time claims are inconsistent.")


@dataclass(frozen=True)
class FinanceServiceTrustPolicy:
    """Deployment-owned trust settings; never supplied by the calling service."""

    trusted_issuer: str
    expected_audience: str
    allowed_subjects: FrozenSet[str]
    maximum_lifetime_seconds: int = 300
    clock_skew_seconds: int = 30

    def __post_init__(self) -> None:
        for value, field in (
            (self.trusted_issuer, "trusted_issuer"),
            (self.expected_audience, "expected_audience"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ServiceAuthorizationError(f"{field} is required.")
        if not isinstance(self.allowed_subjects, (set, frozenset)) or not self.allowed_subjects:
            raise ServiceAuthorizationError("An explicit service-subject allowlist is required.")
        if any(not isinstance(item, str) or not item.strip() for item in self.allowed_subjects):
            raise ServiceAuthorizationError("Allowed service subjects must be non-empty strings.")
        if isinstance(self.maximum_lifetime_seconds, bool) or not isinstance(self.maximum_lifetime_seconds, int) or not 1 <= self.maximum_lifetime_seconds <= 3600:
            raise ServiceAuthorizationError("maximum_lifetime_seconds must be between 1 and 3600.")
        if isinstance(self.clock_skew_seconds, bool) or not isinstance(self.clock_skew_seconds, int) or not 0 <= self.clock_skew_seconds <= 120:
            raise ServiceAuthorizationError("clock_skew_seconds must be between 0 and 120.")


@dataclass(frozen=True)
class AuthorizedFinanceService:
    """Narrow authorization result; contains no bearer token or account mapping."""

    issuer: str
    subject: str
    scopes: FrozenSet[str]
    environment: Literal["demo"]
    token_id: str
    expires_at: int


class FinanceReplayStore(Protocol):
    """Durable store implementing an atomic, single-use token-ID claim.

    Implementations must atomically reject an existing token_id and retain a
    new ID until expires_at plus the configured clock-skew window. Storage
    errors must fail closed; a process-local dictionary is not production-safe.
    """

    def consume_once(self, token_id: str, *, expires_at: int) -> bool:
        """Return true only when this token ID was atomically recorded first."""
        ...


def require_unreplayed_finance_service(
    principal: AuthorizedFinanceService,
    replay_store: FinanceReplayStore,
    *,
    now: datetime | None = None,
    clock_skew_seconds: int = 0,
) -> AuthorizedFinanceService:
    """Atomically consume a verified token ID before allowing a Finance read.

    This is only a storage contract and enforcement seam. No production store
    is supplied here; callers must inject a durable atomic implementation.
    """
    if not isinstance(principal, AuthorizedFinanceService):
        raise TypeError("An authorized Finance service principal is required.")
    if isinstance(clock_skew_seconds, bool) or not isinstance(clock_skew_seconds, int) or not 0 <= clock_skew_seconds <= 120:
        raise ServiceAuthorizationError("clock_skew_seconds must be between 0 and 120.")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ServiceAuthorizationError("now must be timezone-aware.")
    if int(current.timestamp()) > principal.expires_at + clock_skew_seconds:
        raise ServiceAuthorizationError("Service token has expired before replay check.")
    if not callable(getattr(replay_store, "consume_once", None)):
        raise TypeError("A durable FinanceReplayStore implementation is required.")
    if replay_store.consume_once(principal.token_id, expires_at=principal.expires_at) is not True:
        raise ServiceAuthorizationError("Service token replay detected.")
    return principal


def authorize_finance_service(
    claims: VerifiedServiceTokenClaims,
    policy: FinanceServiceTrustPolicy,
    *,
    now: datetime | None = None,
) -> AuthorizedFinanceService:
    """Validate trusted claims for Demo portfolio reads only.

    The caller must obtain claims from an audited signature-verifying adapter.
    This function does not provide signature verification or replay protection.
    """
    if not isinstance(claims, VerifiedServiceTokenClaims):
        raise TypeError("VerifiedServiceTokenClaims from a trusted verifier are required.")
    if not isinstance(policy, FinanceServiceTrustPolicy):
        raise TypeError("A deployment-owned FinanceServiceTrustPolicy is required.")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ServiceAuthorizationError("now must be timezone-aware.")
    timestamp = int(current.timestamp())
    skew = policy.clock_skew_seconds
    if claims.issuer != policy.trusted_issuer:
        raise ServiceAuthorizationError("Untrusted service-token issuer.")
    if claims.audience != policy.expected_audience:
        raise ServiceAuthorizationError("Service token audience does not match this API.")
    if claims.subject not in policy.allowed_subjects:
        raise ServiceAuthorizationError("Service principal is not on the allowlist.")
    if claims.issued_at > timestamp + skew:
        raise ServiceAuthorizationError("Service token issued-at time is in the future.")
    if claims.not_before > timestamp + skew:
        raise ServiceAuthorizationError("Service token is not active yet.")
    if claims.expires_at < timestamp - skew:
        raise ServiceAuthorizationError("Service token has expired.")
    if claims.expires_at - claims.issued_at > policy.maximum_lifetime_seconds:
        raise ServiceAuthorizationError("Service token lifetime exceeds policy.")
    if FINANCE_PORTFOLIO_READ not in claims.scopes:
        raise ServiceAuthorizationError("Read-only Finance portfolio scope is required.")
    return AuthorizedFinanceService(
        issuer=claims.issuer,
        subject=claims.subject,
        scopes=frozenset(claims.scopes),
        environment="demo",
        token_id=claims.token_id,
        expires_at=claims.expires_at,
    )
