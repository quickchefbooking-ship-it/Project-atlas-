import json

import pytest

from atlas_market import (
    Instrument,
    MarketDataValidationError,
    build_synthetic_market_snapshot,
    build_watchlist_read_model,
    serialize_watchlist_read_model,
)


def _assert_no_floats(value):
    if isinstance(value, float):
        pytest.fail("market payload must not contain binary floating-point values")
    if isinstance(value, dict):
        for nested in value.values():
            _assert_no_floats(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_floats(nested)


def test_watchlist_serializer_is_json_compatible_and_preserves_decimal_strings():
    snapshot = build_synthetic_market_snapshot()

    payload = serialize_watchlist_read_model(snapshot)
    encoded = json.dumps(payload, allow_nan=False, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["schema_version"] == 1
    assert decoded["mode"] == "read_only"
    assert len(decoded["items"]) == 3
    _assert_no_floats(decoded)

    for item in decoded["items"]:
        assert item["availability"] == "available"
        assert item["data_status"] == "synthetic"
        assert item["provenance"]["source_id"] == "atlas:synthetic-demo"
        assert item["provenance"]["source_version"] == "1"
        assert isinstance(item["latest_close"], str)
        assert isinstance(item["change_percent"], str)
        assert item["chart_points"]
        for point in item["chart_points"]:
            assert point["data_status"] == "synthetic"
            assert point["source_id"] == "atlas:synthetic-demo"
            assert isinstance(point["open"], str)
            assert isinstance(point["high"], str)
            assert isinstance(point["low"], str)
            assert isinstance(point["close"], str)
            assert isinstance(point["volume"], str)


def test_watchlist_serializer_keeps_unavailable_instruments_without_prices():
    instrument = Instrument(
        instrument_id="equity:demo-unavailable.xdemo",
        symbol="NONE",
        display_name="Unavailable Demo Instrument",
        asset_class="equity",
        venue="DEMO",
        quote_currency="USD",
    )
    unavailable, = build_watchlist_read_model([instrument], {})

    payload = serialize_watchlist_read_model([unavailable])
    item, = payload["items"]

    assert item["availability"] == "unavailable"
    assert item["data_status"] == "unavailable"
    assert item["provenance"] is None
    assert item["latest_close"] is None
    assert item["change_percent"] is None
    assert item["chart_points"] == []


def test_watchlist_serializer_rejects_invalid_sequences_items_and_duplicate_ids():
    snapshot = build_synthetic_market_snapshot()

    with pytest.raises(MarketDataValidationError, match="ordered watchlist sequence"):
        serialize_watchlist_read_model("not-a-sequence")

    with pytest.raises(MarketDataValidationError, match="WatchlistItem"):
        serialize_watchlist_read_model([object()])

    with pytest.raises(MarketDataValidationError, match="duplicate instrument"):
        serialize_watchlist_read_model([snapshot[0], snapshot[0]])
