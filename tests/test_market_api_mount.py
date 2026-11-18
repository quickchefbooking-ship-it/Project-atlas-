from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from atlas_market.integration import mount_market_watchlist_router


def _auth(x_api_key: str | None = Header(default=None)):
    if x_api_key != "test-only-key":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


def _client():
    app = FastAPI()
    mount_market_watchlist_router(app, authentication_dependency=_auth)
    return TestClient(app)


def test_market_router_mount_requires_authentication():
    client = _client()

    assert client.get("/market/watchlist").status_code == 401
    assert client.get("/market/watchlist", headers={"x-api-key": "wrong"}).status_code == 401


def test_authenticated_market_router_mount_returns_synthetic_fixture_only():
    response = _client().get("/market/watchlist", headers={"x-api-key": "test-only-key"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["demo_fixture"] is True
    assert payload["mode"] == "read_only"
    assert all(item["data_status"] == "synthetic" for item in payload["items"])


def test_mount_helper_rejects_missing_auth_dependency():
    app = FastAPI()

    try:
        mount_market_watchlist_router(app, authentication_dependency=None)
    except TypeError as exc:
        assert "authentication dependency is required" in str(exc)
    else:
        raise AssertionError("The mount helper must reject a missing auth dependency.")
