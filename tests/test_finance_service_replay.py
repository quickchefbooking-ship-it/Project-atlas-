from datetime import datetime, timezone

import pytest

from atlas_engine.finance_service_auth import (
    FINANCE_PORTFOLIO_READ,
    FinanceServiceTrustPolicy,
    ServiceAuthorizationError,
    VerifiedServiceTokenClaims,
    authorize_finance_service,
    require_unreplayed_finance_service,
)


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
STAMP = int(NOW.timestamp())


class InMemoryReplayStore:
    """Test double only; never suitable for multi-worker production."""

    def __init__(self):
        self.seen = {}

    def consume_once(self, token_id: str, *, expires_at: int) -> bool:
        if token_id in self.seen:
            return False
        self.seen[token_id] = expires_at
        return True


class BrokenReplayStore:
    def consume_once(self, token_id: str, *, expires_at: int) -> bool:
        raise RuntimeError("replay store unavailable")


def make_principal():
    claims = VerifiedServiceTokenClaims(
        issuer="https://identity.example.test",
        subject="trading-bridge-demo",
        audience="atlas-finance-bridge",
        issued_at=STAMP - 30,
        not_before=STAMP - 30,
        expires_at=STAMP + 120,
        token_id="jti-one-use",
        scopes=(FINANCE_PORTFOLIO_READ,),
        environment="demo",
    )
    policy = FinanceServiceTrustPolicy(
        trusted_issuer="https://identity.example.test",
        expected_audience="atlas-finance-bridge",
        allowed_subjects=frozenset({"trading-bridge-demo"}),
        clock_skew_seconds=0,
    )
    return authorize_finance_service(claims, policy, now=NOW)


def test_replay_store_allows_first_use_and_rejects_second_use():
    principal = make_principal()
    store = InMemoryReplayStore()
    assert require_unreplayed_finance_service(principal, store, now=NOW) is principal
    with pytest.raises(ServiceAuthorizationError, match="replay"):
        require_unreplayed_finance_service(principal, store, now=NOW)


def test_replay_check_fails_closed_when_store_is_unavailable():
    with pytest.raises(RuntimeError, match="unavailable"):
        require_unreplayed_finance_service(make_principal(), BrokenReplayStore(), now=NOW)


def test_replay_check_rejects_expired_principal_before_store_access():
    with pytest.raises(ServiceAuthorizationError, match="expired"):
        require_unreplayed_finance_service(
            make_principal(),
            InMemoryReplayStore(),
            now=datetime.fromtimestamp(STAMP + 121, timezone.utc),
        )


def test_replay_check_requires_timezone_aware_clock():
    with pytest.raises(ServiceAuthorizationError, match="timezone-aware"):
        require_unreplayed_finance_service(
            make_principal(),
            InMemoryReplayStore(),
            now=datetime(2026, 11, 14, 12, 0),
        )
