"""Strict HTTP response schema for the synthetic market watchlist."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, StrictStr


class _StrictContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class MarketInstrumentContract(_StrictContractModel):
    instrument_id: StrictStr
    symbol: StrictStr
    display_name: StrictStr
    asset_class: Literal["equity", "etf", "fx", "crypto", "index", "commodity"]
    venue: StrictStr
    quote_currency: StrictStr


class MarketProvenanceContract(_StrictContractModel):
    source_id: StrictStr
    source_name: StrictStr
    source_version: StrictStr
    venue: StrictStr
    observed_at: StrictStr


class MarketChartPointContract(_StrictContractModel):
    start_at: StrictStr
    end_at: StrictStr
    timezone: Literal["UTC"]
    open: StrictStr
    high: StrictStr
    low: StrictStr
    close: StrictStr
    volume: StrictStr
    complete: StrictBool
    source_id: StrictStr
    source_version: StrictStr
    venue: StrictStr
    observed_at: StrictStr
    delay_seconds: StrictInt | None
    # This endpoint serves a synthetic fixture only. Other market-quality
    # states belong to a future separately reviewed provider-backed contract.
    data_status: Literal["synthetic"]


class MarketWatchlistItemContract(_StrictContractModel):
    instrument: MarketInstrumentContract
    availability: Literal["available", "unavailable"]
    # Do not let the synthetic demo endpoint claim delayed, indicative or live data.
    data_status: Literal["synthetic", "unavailable"]
    provenance: MarketProvenanceContract | None
    interval: StrictStr | None
    last_bar_end: StrictStr | None
    last_observed_at: StrictStr | None
    latest_close: StrictStr | None
    change_percent: StrictStr | None
    chart_points: list[MarketChartPointContract]


class MarketWatchlistResponse(_StrictContractModel):
    schema_version: Literal[1]
    mode: Literal["read_only"]
    items: list[MarketWatchlistItemContract]
    demo_fixture: Literal[True]
    notice: StrictStr
