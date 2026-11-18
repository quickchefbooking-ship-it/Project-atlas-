"""Deterministic synthetic-only sample market snapshot for UI and integration tests.

All records use fixed timestamps and explicit synthetic provenance. This module
contains no provider clients, clock access, network calls, persistence or orders.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .market_data import (
    Instrument,
    MarketDataProvenance,
    OHLCVBar,
    WatchlistItem,
    build_watchlist_read_model,
)


_BASE_START = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)
_SOURCE_ID = "atlas:synthetic-demo"
_SOURCE_NAME = "Atlas synthetic demonstration fixture"
_SOURCE_VERSION = "1"
_INTERVAL = "1h"

_DEMO_INSTRUMENTS = (
    Instrument(
        instrument_id="equity:demo-acme.xdemo",
        symbol="ACME",
        display_name="Acme Demo Equity",
        asset_class="equity",
        venue="DEMO",
        quote_currency="USD",
    ),
    Instrument(
        instrument_id="fx:eur-usd.demo",
        symbol="EUR/USD",
        display_name="Euro / US Dollar Demo",
        asset_class="fx",
        venue="DEMO",
        quote_currency="USD",
    ),
    Instrument(
        instrument_id="crypto:btc-usd.demo",
        symbol="BTC/USD",
        display_name="Bitcoin / US Dollar Demo",
        asset_class="crypto",
        venue="DEMO",
        quote_currency="USD",
    ),
)

# Fixed decimal strings keep the fixture deterministic across platforms and runs.
_DEMO_PRICES = {
    "equity:demo-acme.xdemo": ("100.00", "102.00", "101.00"),
    "fx:eur-usd.demo": ("1.1500", "1.1510", "1.1490"),
    "crypto:btc-usd.demo": ("90000.00", "90500.00", "91000.00"),
}
_DEMO_VOLUMES = {
    "equity:demo-acme.xdemo": "1250",
    "fx:eur-usd.demo": "250000",
    "crypto:btc-usd.demo": "3.5",
}


def build_synthetic_market_snapshot() -> tuple[WatchlistItem, ...]:
    """Return a stable, visibly synthetic multi-asset watchlist/chart snapshot."""
    bars_by_instrument: dict[str, tuple[OHLCVBar, ...]] = {}

    for instrument in _DEMO_INSTRUMENTS:
        bars: list[OHLCVBar] = []
        prices = _DEMO_PRICES[instrument.instrument_id]
        for index, close_value in enumerate(prices):
            start_at = _BASE_START + timedelta(hours=index)
            end_at = start_at + timedelta(hours=1)
            open_value = prices[index - 1] if index else close_value
            open_number = float(open_value)
            close_number = float(close_value)
            high_value = str(max(open_number, close_number) * 1.01)
            low_value = str(min(open_number, close_number) * 0.99)
            provenance = MarketDataProvenance(
                source_id=_SOURCE_ID,
                source_name=_SOURCE_NAME,
                source_version=_SOURCE_VERSION,
                venue=instrument.venue,
                observed_at=end_at + timedelta(minutes=1),
                data_status="synthetic",
            )
            bars.append(OHLCVBar(
                instrument_id=instrument.instrument_id,
                interval=_INTERVAL,
                start_at=start_at,
                end_at=end_at,
                open=open_value,
                high=high_value,
                low=low_value,
                close=close_value,
                volume=_DEMO_VOLUMES[instrument.instrument_id],
                complete=True,
                provenance=provenance,
            ))
        bars_by_instrument[instrument.instrument_id] = tuple(bars)

    return build_watchlist_read_model(_DEMO_INSTRUMENTS, bars_by_instrument)
