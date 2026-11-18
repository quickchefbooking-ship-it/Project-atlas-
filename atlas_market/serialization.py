"""Stable JSON-safe serialization for read-only market watchlists."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from .market_data import (
    DATA_STATUSES,
    ChartPoint,
    Instrument,
    MarketDataValidationError,
    WatchlistItem,
)


def _decimal_text(value: object, field_name: str) -> str | None:
    """Preserve decimal precision at the transport boundary."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Decimal) or not value.is_finite():
        raise MarketDataValidationError(f"{field_name} must be a finite Decimal or None")
    return str(value)


def _chart_point_payload(point: ChartPoint) -> dict[str, object]:
    if not isinstance(point, ChartPoint):
        raise MarketDataValidationError("every chart point must be a ChartPoint")
    return {
        "start_at": point.start_at,
        "end_at": point.end_at,
        "timezone": point.timezone,
        "open": point.open,
        "high": point.high,
        "low": point.low,
        "close": point.close,
        "volume": point.volume,
        "complete": point.complete,
        "source_id": point.source_id,
        "source_version": point.source_version,
        "venue": point.venue,
        "observed_at": point.observed_at,
        "delay_seconds": point.delay_seconds,
        "data_status": point.data_status,
    }


def serialize_watchlist_read_model(
    items: Sequence[WatchlistItem],
) -> dict[str, object]:
    """Return a deterministic JSON-compatible, read-only watchlist payload.

    Decimal prices and percentage changes are encoded as strings so JSON
    consumers cannot silently round financial values through binary floats.
    Provenance and quality labels remain attached to every available item and
    every chart point. Unavailable instruments remain visible without prices.
    """
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        raise MarketDataValidationError("items must be an ordered watchlist sequence")

    serialized_items: list[dict[str, object]] = []
    seen_instrument_ids: set[str] = set()

    for item in items:
        if not isinstance(item, WatchlistItem):
            raise MarketDataValidationError("every watchlist item must be a WatchlistItem")
        if not isinstance(item.instrument, Instrument):
            raise MarketDataValidationError("every watchlist item must contain an Instrument")

        instrument = item.instrument
        if instrument.instrument_id in seen_instrument_ids:
            raise MarketDataValidationError("watchlist contains duplicate instrument identifiers")
        seen_instrument_ids.add(instrument.instrument_id)

        if item.availability not in {"available", "unavailable"}:
            raise MarketDataValidationError("watchlist availability is not supported")
        if item.data_status not in DATA_STATUSES | {"unavailable"}:
            raise MarketDataValidationError("watchlist data_status is not supported")
        if not isinstance(item.chart_points, Sequence) or isinstance(item.chart_points, (str, bytes)):
            raise MarketDataValidationError("chart_points must be an ordered sequence")

        provenance = None
        if item.source_id is not None:
            provenance = {
                "source_id": item.source_id,
                "source_name": item.source_name,
                "source_version": item.source_version,
                "venue": instrument.venue,
                "observed_at": item.last_observed_at,
            }

        serialized_items.append({
            "instrument": {
                "instrument_id": instrument.instrument_id,
                "symbol": instrument.symbol,
                "display_name": instrument.display_name,
                "asset_class": instrument.asset_class,
                "venue": instrument.venue,
                "quote_currency": instrument.quote_currency,
            },
            "availability": item.availability,
            "data_status": item.data_status,
            "provenance": provenance,
            "interval": item.interval,
            "last_bar_end": item.last_bar_end,
            "last_observed_at": item.last_observed_at,
            "latest_close": _decimal_text(item.latest_close, "latest_close"),
            "change_percent": _decimal_text(item.change_percent, "change_percent"),
            "chart_points": [_chart_point_payload(point) for point in item.chart_points],
        })

    return {
        "schema_version": 1,
        "mode": "read_only",
        "items": serialized_items,
    }
