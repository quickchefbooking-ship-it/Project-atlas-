"""Read-only Finance arm contract for an explicitly authorized TRADING bridge.

This is an Atlas-side normalized boundary, not a Trading 212 client. It accepts
already-normalized data from a future authenticated adapter. It stores no
broker credentials, performs no HTTP calls, and exposes no order operations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol


MAX_POSITIONS = 2_000
MAX_CURRENCY = 3
MAX_INSTRUMENT_ID = 128
MAX_NAME = 160


def _nonblank(value: str, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{field} must be a non-empty string of at most {limit} characters.")
    return value.strip()


def _money(value: Decimal | str | int, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, str, int)):
        raise ValueError(f"{field} must be a decimal-compatible amount.")
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a valid decimal amount.") from exc
    if not amount.is_finite():
        raise ValueError(f"{field} must be finite.")
    return amount


@dataclass(frozen=True)
class FinanceConnectionProvenance:
    """Non-secret evidence describing the source of a read-only snapshot."""

    source: Literal["trading_bridge"]
    environment: Literal["demo", "live"]
    account_reference: str
    owner_verified: bool
    broker_authenticated: bool
    fetched_at: datetime
    source_request_id: str

    def __post_init__(self) -> None:
        _nonblank(self.account_reference, "account_reference", 128)
        _nonblank(self.source_request_id, "source_request_id", 128)
        if self.fetched_at.tzinfo is None or self.fetched_at.utcoffset() is None:
            raise ValueError("fetched_at must be timezone-aware.")
        if type(self.owner_verified) is not bool or type(self.broker_authenticated) is not bool:
            raise ValueError("Verification flags must be booleans.")
        if not self.owner_verified or not self.broker_authenticated:
            raise ValueError("Unverified account data cannot enter the Finance arm.")


@dataclass(frozen=True)
class FinancePosition:
    instrument_id: str
    name: str
    currency: str
    quantity: Decimal
    market_value: Decimal
    cost_basis: Decimal | None = None

    def __post_init__(self) -> None:
        _nonblank(self.instrument_id, "instrument_id", MAX_INSTRUMENT_ID)
        _nonblank(self.name, "name", MAX_NAME)
        _nonblank(self.currency, "currency", MAX_CURRENCY)
        object.__setattr__(self, "quantity", _money(self.quantity, "quantity"))
        object.__setattr__(self, "market_value", _money(self.market_value, "market_value"))
        if self.cost_basis is not None:
            object.__setattr__(self, "cost_basis", _money(self.cost_basis, "cost_basis"))


@dataclass(frozen=True)
class FinancePortfolioSnapshot:
    provenance: FinanceConnectionProvenance
    base_currency: str
    cash_balance: Decimal
    total_value: Decimal
    positions: tuple[FinancePosition, ...]

    def __post_init__(self) -> None:
        _nonblank(self.base_currency, "base_currency", MAX_CURRENCY)
        object.__setattr__(self, "cash_balance", _money(self.cash_balance, "cash_balance"))
        object.__setattr__(self, "total_value", _money(self.total_value, "total_value"))
        if not isinstance(self.positions, tuple):
            raise ValueError("positions must be an immutable tuple.")
        if len(self.positions) > MAX_POSITIONS:
            raise ValueError("Portfolio exceeds the supported position limit.")
        if any(not isinstance(position, FinancePosition) for position in self.positions):
            raise ValueError("Every position must use the FinancePosition contract.")
        identifiers = [position.instrument_id for position in self.positions]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Position instrument IDs must be unique within a snapshot.")


class ReadOnlyFinanceSource(Protocol):
    """Narrow read capability. This contract deliberately has no order methods."""

    name: str

    def get_portfolio_snapshot(self) -> FinancePortfolioSnapshot:
        """Return a verified, normalized portfolio snapshot."""
        ...


def require_fresh_snapshot(
    snapshot: FinancePortfolioSnapshot,
    *,
    now: datetime | None = None,
    max_age_seconds: int = 300,
) -> FinancePortfolioSnapshot:
    """Reject stale or future-dated snapshots before presenting them as current."""
    if not isinstance(snapshot, FinancePortfolioSnapshot):
        raise TypeError("A FinancePortfolioSnapshot is required.")
    if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int) or not 1 <= max_age_seconds <= 86_400:
        raise ValueError("max_age_seconds must be between 1 and 86400.")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware.")
    age = (current - snapshot.provenance.fetched_at).total_seconds()
    if age < 0:
        raise ValueError("Snapshot timestamp cannot be in the future.")
    if age > max_age_seconds:
        raise ValueError("Portfolio snapshot is stale and must be refreshed.")
    return snapshot
