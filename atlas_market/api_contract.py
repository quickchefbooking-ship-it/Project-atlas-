"""Strict HTTP response schema for the synthetic market watchlist."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, StrictStr, model_validator


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

    @model_validator(mode="after")
    def validate_availability_consistency(self) -> "MarketWatchlistItemContract":
        """Keep availability, provenance and price fields internally consistent."""
        if self.availability == "unavailable":
            if self.data_status != "unavailable" or any(
                value is not None
                for value in (
                    self.provenance,
                    self.interval,
                    self.last_bar_end,
                    self.last_observed_at,
                    self.latest_close,
                    self.change_percent,
                )
            ) or self.chart_points:
                raise ValueError(
                    "unavailable items must use unavailable status and contain no market data"
                )
            return self

        if (
            self.data_status != "synthetic"
            or self.provenance is None
            or self.interval is None
            or self.last_bar_end is None
            or self.last_observed_at is None
            or self.latest_close is None
            or not self.chart_points
        ):
            raise ValueError(
                "available synthetic items must include provenance, price metadata and chart points"
            )
        return self


class MarketWatchlistResponse(_StrictContractModel):
    schema_version: Literal[1]
    mode: Literal["read_only"]
    items: list[MarketWatchlistItemContract]
    demo_fixture: Literal[True]
    notice: StrictStr
