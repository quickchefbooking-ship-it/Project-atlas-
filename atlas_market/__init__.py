"""Isolated, read-only market-data contracts for Atlas Market Intelligence."""

from .market_data import (
    ASSET_CLASSES,
    DATA_STATUSES,
    ChartPoint,
    Instrument,
    MarketDataProvenance,
    MarketDataValidationError,
    OHLCVBar,
    WatchlistItem,
    build_watchlist_read_model,
    validate_series,
)
from .serialization import serialize_watchlist_read_model
from .synthetic import build_synthetic_market_snapshot

__all__ = [
    "ASSET_CLASSES",
    "DATA_STATUSES",
    "ChartPoint",
    "Instrument",
    "MarketDataProvenance",
    "MarketDataValidationError",
    "OHLCVBar",
    "WatchlistItem",
    "build_synthetic_market_snapshot",
    "build_watchlist_read_model",
    "serialize_watchlist_read_model",
    "validate_series",
]
