import json

import pytest
from pydantic import ValidationError

from atlas_market.api_contract import MarketWatchlistResponse
from atlas_market import build_synthetic_market_snapshot, serialize_watchlist_read_model


def _payload():
    payload = serialize_watchlist_read_model(build_synthetic_market_snapshot())
    payload["demo_fixture"] = True
    payload["notice"] = "Synthetic demonstration data only; not live market observations."
    return payload


def _make_unavailable(item):
    item.update(
        availability="unavailable",
        data_status="unavailable",
        provenance=None,
        interval=None,
        last_bar_end=None,
        last_observed_at=None,
        latest_close=None,
        change_percent=None,
        chart_points=[],
    )
    return item


def test_response_contract_accepts_the_synthetic_watchlist():
    validated = MarketWatchlistResponse.model_validate(_payload())

    assert validated.schema_version == 1
    assert validated.mode == "read_only"
    assert validated.demo_fixture is True
    assert len(validated.items) == 3


def test_response_contract_rejects_binary_float_financial_values():
    payload = _payload()
    payload["items"][0]["latest_close"] = 1.23

    with pytest.raises(ValidationError):
        MarketWatchlistResponse.model_validate(payload)


def test_response_contract_rejects_unexpected_fields():
    payload = _payload()
    payload["unreviewed_field"] = "not part of the contract"

    with pytest.raises(ValidationError):
        MarketWatchlistResponse.model_validate(payload)


@pytest.mark.parametrize(
    ("target", "status"),
    [
        ("item", "live"),
        ("item", "delayed"),
        ("item", "indicative"),
        ("chart_point", "live"),
        ("chart_point", "delayed"),
        ("chart_point", "indicative"),
    ],
)
def test_synthetic_response_contract_rejects_non_synthetic_provenance(target, status):
    payload = _payload()
    if target == "item":
        payload["items"][0]["data_status"] = status
    else:
        payload["items"][0]["chart_points"][0]["data_status"] = status

    with pytest.raises(ValidationError):
        MarketWatchlistResponse.model_validate(payload)


def test_response_contract_accepts_a_consistent_unavailable_item():
    payload = _payload()
    item = _make_unavailable(payload["items"][0])

    validated = MarketWatchlistResponse.model_validate(payload)

    assert validated.items[0].availability == "unavailable"
    assert validated.items[0].data_status == "unavailable"
    assert validated.items[0].provenance is None
    assert validated.items[0].latest_close is None
    assert validated.items[0].chart_points == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("data_status", "synthetic"),
        (
            "provenance",
            {
                "source_id": "atlas:synthetic-demo",
                "source_name": "Synthetic fixture",
                "source_version": "1",
                "venue": "DEMO",
                "observed_at": "2026-11-17T12:01:00+00:00",
            },
        ),
        ("latest_close", "101.00"),
        ("chart_points", [{"data_status": "synthetic"}]),
    ],
)
def test_unavailable_item_rejects_status_provenance_and_price_data(field, value):
    payload = _payload()
    item = _make_unavailable(payload["items"][0])
    item[field] = value

    with pytest.raises(ValidationError):
        MarketWatchlistResponse.model_validate(payload)


def test_available_item_requires_synthetic_provenance_and_chart_data():
    payload = _payload()
    payload["items"][0]["provenance"] = None

    with pytest.raises(ValidationError):
        MarketWatchlistResponse.model_validate(payload)


def test_available_item_rejects_unavailable_data_status():
    payload = _payload()
    payload["items"][0]["data_status"] = "unavailable"

    with pytest.raises(ValidationError):
        MarketWatchlistResponse.model_validate(payload)


def test_openapi_uses_the_versioned_response_model():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from atlas_market.api import router

    app = FastAPI()
    app.include_router(router)
    schema = TestClient(app).get("/openapi.json").json()
    response_schema = schema["paths"]["/market/watchlist"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]

    assert response_schema["$ref"] == "#/components/schemas/MarketWatchlistResponse"
    json.dumps(schema, allow_nan=False)
