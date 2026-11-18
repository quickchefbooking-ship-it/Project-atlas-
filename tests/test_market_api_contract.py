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
