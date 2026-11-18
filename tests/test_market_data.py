from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from atlas_market import (
    Instrument,
    MarketDataProvenance,
    MarketDataValidationError,
    OHLCVBar,
    build_watchlist_read_model,
    validate_series,
)


START = datetime(2026, 11, 18, 9, 0, tzinfo=timezone.utc)
INSTRUMENT = Instrument(
    instrument_id="equity:acme.xnys",
    symbol="ACME",
    display_name="Acme Example",
    asset_class="equity",
    venue="XNYS",
    quote_currency="USD",
)


def provenance(*, source_id="fixture:market-v1", status="synthetic", venue="XNYS", observed_at=None):
    return MarketDataProvenance(
        source_id=source_id,
        source_name="Atlas synthetic fixture",
        source_version="1",
        venue=venue,
        observed_at=observed_at or START + timedelta(hours=1),
        data_status=status,
    )


def candle(
    offset=0,
    *,
    open_value="100",
    high="112",
    low="98",
    close="110",
    volume="25",
    instrument_id=INSTRUMENT.instrument_id,
    interval="1h",
    source=None,
    complete=True,
):
    start = START + timedelta(hours=offset)
    duration = timedelta(hours=1) if interval == "1h" else timedelta(minutes=5)
    return OHLCVBar(
        instrument_id=instrument_id,
        interval=interval,
        start_at=start,
        end_at=start + duration,
        open=open_value,
        high=high,
        low=low,
        close=close,
        volume=volume,
        complete=complete,
        provenance=source or provenance(observed_at=start + duration),
    )


def test_synthetic_candle_normalises_values_and_timestamps_to_utc():
    local_start = datetime(2026, 11, 18, 10, 0, tzinfo=timezone(timedelta(hours=1)))
    bar = OHLCVBar(
        instrument_id=INSTRUMENT.instrument_id,
        interval="1h",
        start_at=local_start,
        end_at=local_start + timedelta(hours=1),
        open="100.25",
        high="112.50",
        low="98.75",
        close="110.00",
        volume="25.5",
        complete=True,
        provenance=provenance(observed_at=local_start + timedelta(hours=1)),
    )

    assert bar.start_at == START
    assert bar.end_at == START + timedelta(hours=1)
    assert bar.timezone == "UTC"
    assert bar.open == Decimal("100.25")
    assert bar.volume == Decimal("25.5")
    assert bar.provenance.data_status == "synthetic"


@pytest.mark.parametrize(
    "values",
    [
        {"open_value": "100", "high": "99", "low": "95", "close": "98"},
        {"open_value": "100", "high": "110", "low": "101", "close": "105"},
        {"open_value": "100", "high": "110", "low": "95", "close": "111"},
    ],
)
def test_candle_rejects_impossible_ohlc_relationships(values):
    with pytest.raises(MarketDataValidationError):
        candle(**values)


@pytest.mark.parametrize("bad_value", ["NaN", "Infinity", "-Infinity", "not-a-price", True])
def test_candle_rejects_non_finite_or_non_decimal_prices(bad_value):
    with pytest.raises(MarketDataValidationError):
        candle(open_value=bad_value)


def test_candle_rejects_zero_or_negative_prices_and_negative_volume():
    with pytest.raises(MarketDataValidationError):
        candle(open_value="0")
    with pytest.raises(MarketDataValidationError):
        candle(close="-1")
    with pytest.raises(MarketDataValidationError):
        candle(volume="-0.01")


def test_candle_rejects_naive_timestamps_and_interval_mismatch():
    with pytest.raises(MarketDataValidationError, match="timezone-aware"):
        OHLCVBar(
            instrument_id=INSTRUMENT.instrument_id,
            interval="1h",
            start_at=datetime(2026, 11, 18, 9, 0),
            end_at=datetime(2026, 11, 18, 10, 0),
            open="100", high="110", low="90", close="105", volume="1",
            complete=True, provenance=provenance(),
        )
    with pytest.raises(MarketDataValidationError, match="exactly match interval"):
        candle(interval="5m")


def test_candle_rejects_invalid_completeness_and_provenance_status():
    with pytest.raises(MarketDataValidationError, match="complete must be a boolean"):
        candle(complete=1)
    with pytest.raises(MarketDataValidationError, match="data_status"):
        provenance(status="unknown")


def test_series_rejects_duplicate_out_of_order_and_overlapping_bars():
    first = candle(offset=0)
    duplicate = candle(offset=0)
    earlier = candle(offset=-1)
    overlapping = OHLCVBar(
        instrument_id=INSTRUMENT.instrument_id,
        interval="1h",
        start_at=START + timedelta(minutes=30),
        end_at=START + timedelta(hours=1, minutes=30),
        open="100", high="112", low="98", close="110", volume="25",
        complete=True, provenance=provenance(),
    )

    with pytest.raises(MarketDataValidationError, match="duplicate"):
        validate_series([first, duplicate])
    with pytest.raises(MarketDataValidationError, match="out of order"):
        validate_series([first, earlier])
    with pytest.raises(MarketDataValidationError, match="overlap"):
        validate_series([first, overlapping])


def test_series_rejects_mixed_instrument_interval_and_provenance():
    first = candle(offset=0)
    wrong_instrument = candle(offset=1, instrument_id="equity:other.xnys")
    wrong_interval = candle(offset=1, interval="5m")
    wrong_source = candle(offset=1, source=provenance(source_id="fixture:other"))

    with pytest.raises(MarketDataValidationError, match="instrument"):
        validate_series([first, wrong_instrument])
    with pytest.raises(MarketDataValidationError, match="interval"):
        validate_series([first, wrong_interval])
    with pytest.raises(MarketDataValidationError, match="provenance"):
        validate_series([first, wrong_source])


def test_series_preserves_gaps_instead_of_fabricating_missing_candles():
    first = candle(offset=0)
    third = candle(offset=2)

    assert validate_series([first, third]) == (first, third)


def test_watchlist_read_model_exposes_synthetic_provenance_and_chart_points():
    first = candle(offset=0, open_value="100", high="105", low="99", close="100")
    second = candle(offset=1, open_value="100", high="112", low="98", close="110", complete=False)

    item, = build_watchlist_read_model(
        [INSTRUMENT],
        {INSTRUMENT.instrument_id: [first, second]},
    )

    assert item.availability == "available"
    assert item.data_status == "synthetic"
    assert item.source_id == "fixture:market-v1"
    assert item.source_name == "Atlas synthetic fixture"
    assert item.source_version == "1"
    assert item.interval == "1h"
    assert item.latest_close == Decimal("110")
    assert item.change_percent == Decimal("10")
    assert len(item.chart_points) == 2
    assert item.chart_points[-1].close == "110"
    assert item.chart_points[-1].complete is False
    assert item.chart_points[-1].data_status == "synthetic"
    assert item.last_observed_at.endswith("+00:00")


def test_watchlist_keeps_instruments_without_data_visible_as_unavailable():
    item, = build_watchlist_read_model([INSTRUMENT], {})

    assert item.availability == "unavailable"
    assert item.data_status == "unavailable"
    assert item.latest_close is None
    assert item.change_percent is None
    assert item.chart_points == ()


def test_watchlist_rejects_duplicate_ids_unknown_series_and_venue_mismatch():
    with pytest.raises(MarketDataValidationError, match="duplicate instrument"):
        build_watchlist_read_model([INSTRUMENT, INSTRUMENT], {})

    with pytest.raises(MarketDataValidationError, match="outside the watchlist"):
        build_watchlist_read_model([INSTRUMENT], {"equity:other.xnys": [candle()]})

    wrong_venue = candle(source=provenance(venue="XLON"))
    with pytest.raises(MarketDataValidationError, match="venue"):
        build_watchlist_read_model(
            [INSTRUMENT],
            {INSTRUMENT.instrument_id: [wrong_venue]},
        )


def test_watchlist_requires_ordered_non_empty_series_when_data_is_supplied():
    with pytest.raises(MarketDataValidationError, match="non-empty ordered sequence"):
        validate_series([])
    with pytest.raises(MarketDataValidationError, match="OHLCVBar"):
        validate_series([{"close": "100"}])
