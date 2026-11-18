"""Canonical, read-only market-data contracts and watchlist projections.

This module has no provider clients, persistence, broker APIs or order execution.
Synthetic fixtures are represented explicitly in provenance and remain visibly
labelled in the chart/watchlist read model.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re


ASSET_CLASSES = frozenset({"equity", "etf", "fx", "crypto", "index", "commodity"})
DATA_STATUSES = frozenset({"synthetic", "delayed", "indicative", "live"})
_INTERVAL_PATTERN = re.compile(r"^([1-9][0-9]*)(m|h|d)$")
_INSTRUMENT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,63}$")
_CURRENCY_PATTERN = re.compile(r"^[A-Z0-9]{3,8}$")


class MarketDataValidationError(ValueError):
    """Raised when market data cannot be safely normalised or displayed."""


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketDataValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _aware_utc(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MarketDataValidationError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _decimal_value(value: object, field_name: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise MarketDataValidationError(f"{field_name} must be a finite decimal")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise MarketDataValidationError(f"{field_name} must be a finite decimal") from None
    if not result.is_finite():
        raise MarketDataValidationError(f"{field_name} must be a finite decimal")
    if positive and result <= 0:
        raise MarketDataValidationError(f"{field_name} must be greater than zero")
    return result


def _interval_duration(interval: object) -> timedelta:
    if not isinstance(interval, str):
        raise MarketDataValidationError("interval must be a supported duration string")
    match = _INTERVAL_PATTERN.fullmatch(interval)
    if match is None:
        raise MarketDataValidationError("interval must use a positive m, h or d duration")
    amount_text = match.group(1)
    if len(amount_text) > 8:
        raise MarketDataValidationError("interval exceeds the supported duration bound")
    amount = int(amount_text)
    unit = match.group(2)
    seconds_per_unit = {"m": 60, "h": 3600, "d": 86400}[unit]
    total_seconds = amount * seconds_per_unit
    if total_seconds > 366 * 86400:
        raise MarketDataValidationError("interval exceeds the supported duration bound")
    return timedelta(seconds=total_seconds)


@dataclass(frozen=True)
class Instrument:
    """Stable instrument identity; a ticker alone is never treated as canonical."""

    instrument_id: str
    symbol: str
    display_name: str
    asset_class: str
    venue: str
    quote_currency: str

    def __post_init__(self) -> None:
        instrument_id = _required_text(self.instrument_id, "instrument_id")
        if not _INSTRUMENT_ID_PATTERN.fullmatch(instrument_id):
            raise MarketDataValidationError("instrument_id must be a stable lowercase canonical identifier")
        object.__setattr__(self, "instrument_id", instrument_id)
        for field_name in ("symbol", "display_name", "venue"):
            object.__setattr__(self, field_name, _required_text(getattr(self, field_name), field_name))
        if not isinstance(self.asset_class, str) or self.asset_class not in ASSET_CLASSES:
            raise MarketDataValidationError("asset_class is not supported")
        currency = _required_text(self.quote_currency, "quote_currency").upper()
        if not _CURRENCY_PATTERN.fullmatch(currency):
            raise MarketDataValidationError("quote_currency must be a bounded uppercase currency/code")
        object.__setattr__(self, "quote_currency", currency)


@dataclass(frozen=True)
class MarketDataProvenance:
    """Origin and quality labels carried with every candle."""

    source_id: str
    source_name: str
    source_version: str
    venue: str
    observed_at: datetime
    data_status: str
    delay_seconds: int | None = None

    def __post_init__(self) -> None:
        for field_name in ("source_id", "source_name", "source_version", "venue"):
            object.__setattr__(self, field_name, _required_text(getattr(self, field_name), field_name))
        object.__setattr__(self, "observed_at", _aware_utc(self.observed_at, "observed_at"))
        if not isinstance(self.data_status, str) or self.data_status not in DATA_STATUSES:
            raise MarketDataValidationError("data_status must be synthetic, delayed, indicative or live")
        if self.delay_seconds is not None:
            if isinstance(self.delay_seconds, bool) or not isinstance(self.delay_seconds, int) or self.delay_seconds < 0:
                raise MarketDataValidationError("delay_seconds must be a non-negative integer or None")


@dataclass(frozen=True)
class OHLCVBar:
    """One fixed-duration OHLCV candle; timestamps are normalised to UTC."""

    instrument_id: str
    interval: str
    start_at: datetime
    end_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    complete: bool
    provenance: MarketDataProvenance

    def __post_init__(self) -> None:
        instrument_id = _required_text(self.instrument_id, "instrument_id")
        if not _INSTRUMENT_ID_PATTERN.fullmatch(instrument_id):
            raise MarketDataValidationError("instrument_id must be a stable lowercase canonical identifier")
        object.__setattr__(self, "instrument_id", instrument_id)

        duration = _interval_duration(self.interval)
        start_at = _aware_utc(self.start_at, "start_at")
        end_at = _aware_utc(self.end_at, "end_at")
        if end_at <= start_at:
            raise MarketDataValidationError("end_at must be after start_at")
        if end_at - start_at != duration:
            raise MarketDataValidationError("candle duration must exactly match interval")
        object.__setattr__(self, "start_at", start_at)
        object.__setattr__(self, "end_at", end_at)

        for field_name in ("open", "high", "low", "close"):
            object.__setattr__(
                self,
                field_name,
                _decimal_value(getattr(self, field_name), field_name, positive=True),
            )
        object.__setattr__(self, "volume", _decimal_value(self.volume, "volume"))
        if self.volume < 0:
            raise MarketDataValidationError("volume must not be negative")
        if not (self.high >= max(self.open, self.close) and self.low <= min(self.open, self.close)):
            raise MarketDataValidationError("OHLC values violate high/low containment")
        if self.high < self.low:
            raise MarketDataValidationError("high must be greater than or equal to low")
        if not isinstance(self.complete, bool):
            raise MarketDataValidationError("complete must be a boolean")
        if not isinstance(self.provenance, MarketDataProvenance):
            raise MarketDataValidationError("provenance must be a MarketDataProvenance record")

    @property
    def timezone(self) -> str:
        """Canonical timezone used by this contract."""
        return "UTC"


@dataclass(frozen=True)
class ChartPoint:
    start_at: str
    end_at: str
    open: str
    high: str
    low: str
    close: str
    volume: str
    complete: bool
    data_status: str


@dataclass(frozen=True)
class WatchlistItem:
    instrument: Instrument
    availability: str
    data_status: str
    source_id: str | None
    source_name: str | None
    source_version: str | None
    interval: str | None
    last_bar_end: str | None
    last_observed_at: str | None
    latest_close: Decimal | None
    change_percent: Decimal | None
    chart_points: tuple[ChartPoint, ...]


def validate_series(bars: Sequence[OHLCVBar]) -> tuple[OHLCVBar, ...]:
    """Validate a single instrument/interval/source series without reordering it.

    Gaps are permitted and remain visible through timestamps. Duplicate,
    overlapping, out-of-order and mixed-provenance series are rejected.
    """
    if not isinstance(bars, Sequence) or isinstance(bars, (str, bytes)) or not bars:
        raise MarketDataValidationError("bars must be a non-empty ordered sequence")
    normalised = tuple(bars)
    if any(not isinstance(bar, OHLCVBar) for bar in normalised):
        raise MarketDataValidationError("every series item must be an OHLCVBar")

    first = normalised[0]
    for previous, current in zip(normalised, normalised[1:]):
        if current.instrument_id != first.instrument_id:
            raise MarketDataValidationError("series cannot mix instrument identifiers")
        if current.interval != first.interval:
            raise MarketDataValidationError("series cannot mix candle intervals")
        if (
            current.provenance.source_id != first.provenance.source_id
            or current.provenance.source_name != first.provenance.source_name
            or current.provenance.source_version != first.provenance.source_version
            or current.provenance.venue != first.provenance.venue
            or current.provenance.data_status != first.provenance.data_status
        ):
            raise MarketDataValidationError("series cannot mix source, venue or data-quality provenance")
        if current.start_at == previous.start_at:
            raise MarketDataValidationError("series contains a duplicate candle")
        if current.start_at < previous.start_at:
            raise MarketDataValidationError("series candles are out of order")
        if current.start_at < previous.end_at:
            raise MarketDataValidationError("series candles overlap")
    return normalised


def build_watchlist_read_model(
    instruments: Sequence[Instrument],
    bars_by_instrument: Mapping[str, Sequence[OHLCVBar]],
) -> tuple[WatchlistItem, ...]:
    """Build a deterministic read-only watchlist/chart projection from fixtures.

    Instruments without bars remain visible with availability='unavailable'.
    Unknown instrument keys and instrument/venue mismatches fail closed.
    """
    if not isinstance(instruments, Sequence) or isinstance(instruments, (str, bytes)):
        raise MarketDataValidationError("instruments must be an ordered sequence")
    if not isinstance(bars_by_instrument, Mapping):
        raise MarketDataValidationError("bars_by_instrument must be a mapping")

    instrument_list = tuple(instruments)
    if any(not isinstance(item, Instrument) for item in instrument_list):
        raise MarketDataValidationError("every watchlist entry must be an Instrument")
    identifiers = [item.instrument_id for item in instrument_list]
    if len(identifiers) != len(set(identifiers)):
        raise MarketDataValidationError("watchlist contains duplicate instrument identifiers")
    unknown_ids = set(bars_by_instrument) - set(identifiers)
    if unknown_ids:
        raise MarketDataValidationError("bar series supplied for an instrument outside the watchlist")

    result: list[WatchlistItem] = []
    for instrument in instrument_list:
        supplied_bars = bars_by_instrument.get(instrument.instrument_id, ())
        if not isinstance(supplied_bars, Sequence) or isinstance(supplied_bars, (str, bytes)):
            raise MarketDataValidationError("each watchlist series must be an ordered candle sequence")
        if not supplied_bars:
            result.append(WatchlistItem(
                instrument=instrument,
                availability="unavailable",
                data_status="unavailable",
                source_id=None,
                source_name=None,
                source_version=None,
                interval=None,
                last_bar_end=None,
                last_observed_at=None,
                latest_close=None,
                change_percent=None,
                chart_points=(),
            ))
            continue

        bars = validate_series(supplied_bars)
        if bars[0].instrument_id != instrument.instrument_id:
            raise MarketDataValidationError("bar series instrument does not match its watchlist key")
        if any(bar.provenance.venue != instrument.venue for bar in bars):
            raise MarketDataValidationError("bar provenance venue does not match instrument venue")

        latest = bars[-1]
        previous_close = bars[-2].close if len(bars) > 1 else None
        change_percent = None
        if previous_close is not None:
            change_percent = ((latest.close - previous_close) / previous_close) * Decimal("100")

        points = tuple(
            ChartPoint(
                start_at=bar.start_at.isoformat(),
                end_at=bar.end_at.isoformat(),
                open=str(bar.open),
                high=str(bar.high),
                low=str(bar.low),
                close=str(bar.close),
                volume=str(bar.volume),
                complete=bar.complete,
                data_status=bar.provenance.data_status,
            )
            for bar in bars
        )
        result.append(WatchlistItem(
            instrument=instrument,
            availability="available",
            data_status=latest.provenance.data_status,
            source_id=latest.provenance.source_id,
            source_name=latest.provenance.source_name,
            source_version=latest.provenance.source_version,
            interval=latest.interval,
            last_bar_end=latest.end_at.isoformat(),
            last_observed_at=latest.provenance.observed_at.isoformat(),
            latest_close=latest.close,
            change_percent=change_percent,
            chart_points=points,
        ))
    return tuple(result)
