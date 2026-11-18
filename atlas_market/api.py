"""Standalone, read-only FastAPI adapter for the synthetic market watchlist.

The router is deliberately not wired into the application root in this slice.
It exposes only deterministic demonstration data and makes no provider calls.
"""
from __future__ import annotations

from fastapi import APIRouter, Response

from . import build_synthetic_market_snapshot, serialize_watchlist_read_model
from .api_contract import MarketWatchlistResponse

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/watchlist", response_model=MarketWatchlistResponse)
def get_synthetic_watchlist(response: Response) -> dict[str, object]:
    """Return the versioned synthetic demo watchlist, never live market data."""
    response.headers["Cache-Control"] = "no-store"
    payload = serialize_watchlist_read_model(build_synthetic_market_snapshot())
    payload["demo_fixture"] = True
    payload["notice"] = "Synthetic demonstration data only; not live market observations."
    return payload
