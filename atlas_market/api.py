"""Standalone, read-only FastAPI adapter for the synthetic market watchlist.

The router is deliberately not wired into the application root in this slice.
It exposes only deterministic demonstration data and makes no provider calls.
"""
from __future__ import annotations

from fastapi import APIRouter

from . import build_synthetic_market_snapshot, serialize_watchlist_read_model

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/watchlist")
def get_synthetic_watchlist() -> dict[str, object]:
    """Return the versioned synthetic demo watchlist, never live market data."""
    payload = serialize_watchlist_read_model(build_synthetic_market_snapshot())
    payload["demo_fixture"] = True
    payload["notice"] = "Synthetic demonstration data only; not live market observations."
    return payload
