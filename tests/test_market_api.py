import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from atlas_market.api import router


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _assert_no_floats(value):
    if isinstance(value, float):
        raise AssertionError("API market payload must not contain binary floats")
    if isinstance(value, dict):
        for nested in value.values():
            _assert_no_floats(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_floats(nested)


def test_read_only_watchlist_route_returns_explicit_synthetic_demo():
    response = _client().get("/market/watchlist")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["mode"] == "read_only"
    assert payload["demo_fixture"] is True
    assert payload["notice"] == (
        "Synthetic demonstration data only; not live market observations."
    )
    assert len(payload["items"]) == 3
    assert {item["instrument"]["asset_class"] for item in payload["items"]} == {
        "equity", "fx", "crypto"
    }
    assert all(item["data_status"] == "synthetic" for item in payload["items"])
    assert all(
        item["provenance"]["source_id"] == "atlas:synthetic-demo"
        for item in payload["items"]
    )
    _assert_no_floats(payload)
    json.dumps(payload, allow_nan=False)


def test_watchlist_route_is_deterministic_and_has_no_live_claims():
    client = _client()

    first = client.get("/market/watchlist").json()
    second = client.get("/market/watchlist").json()

    assert first == second
    assert first["demo_fixture"] is True
    assert all(
        item["data_status"] != "live"
        for item in first["items"]
    )


def test_watchlist_route_does_not_expose_other_paths_or_methods():
    client = _client()

    assert client.post("/market/watchlist").status_code == 405
    trailing_slash_response = client.get("/market/watchlist/")
    assert trailing_slash_response.status_code == 200
    assert trailing_slash_response.json() == client.get("/market/watchlist").json()
