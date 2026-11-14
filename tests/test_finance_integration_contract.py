from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from atlas_engine.finance_integration_contract import (
    FinanceConnectionProvenance,
    FinancePortfolioSnapshot,
    FinancePosition,
    require_fresh_snapshot,
)


def provenance(**overrides):
    values = {
        "source": "trading_bridge",
        "environment": "demo",
        "account_reference": "demo-account-1",
        "owner_verified": True,
        "broker_authenticated": True,
        "fetched_at": datetime.now(timezone.utc),
        "source_request_id": "request-123",
    }
    values.update(overrides)
    return FinanceConnectionProvenance(**values)


def sample_snapshot(**overrides):
    values = {
        "provenance": provenance(),
        "base_currency": "GBP",
        "cash_balance": Decimal("125.50"),
        "total_value": Decimal("1025.50"),
        "positions": (
            FinancePosition(
                instrument_id="instrument-1",
                name="Example holding",
                currency="GBP",
                quantity=Decimal("10"),
                market_value=Decimal("900"),
            ),
        ),
    }
    values.update(overrides)
    return FinancePortfolioSnapshot(**values)


def test_snapshot_requires_verified_owner_and_broker_authentication():
    with pytest.raises(ValueError, match="Unverified"):
        provenance(owner_verified=False)
    with pytest.raises(ValueError, match="Unverified"):
        provenance(broker_authenticated=False)


def test_snapshot_accepts_normalized_read_only_portfolio():
    snapshot = sample_snapshot()
    assert snapshot.cash_balance == Decimal("125.50")
    assert snapshot.positions[0].quantity == Decimal("10")


def test_snapshot_rejects_duplicate_position_ids():
    position = FinancePosition("one", "Holding", "GBP", 1, 10)
    with pytest.raises(ValueError, match="unique"):
        sample_snapshot(positions=(position, position))


def test_snapshot_rejects_non_finite_money():
    with pytest.raises(ValueError, match="finite"):
        FinancePosition("one", "Holding", "GBP", 1, Decimal("NaN"))


def test_snapshot_rejects_mutable_positions_list():
    with pytest.raises(ValueError, match="immutable tuple"):
        sample_snapshot(positions=[])


def test_freshness_gate_accepts_current_snapshot_and_rejects_stale_data():
    now = datetime.now(timezone.utc)
    snapshot = sample_snapshot(provenance=provenance(fetched_at=now - timedelta(seconds=30)))
    assert require_fresh_snapshot(snapshot, now=now, max_age_seconds=60) is snapshot
    with pytest.raises(ValueError, match="stale"):
        require_fresh_snapshot(snapshot, now=now, max_age_seconds=10)


def test_freshness_gate_rejects_future_timestamp():
    now = datetime.now(timezone.utc)
    snapshot = sample_snapshot(provenance=provenance(fetched_at=now + timedelta(seconds=1)))
    with pytest.raises(ValueError, match="future"):
        require_fresh_snapshot(snapshot, now=now)
