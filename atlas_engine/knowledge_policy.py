"""Fail-closed policy filters for approved Source Division retrieval.

This module is a policy layer over the existing lexical retriever. It does not
fetch sources, approve records, or treat source text as instructions.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .source_division import retrieve


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def retrieve_scoped(
    query: str,
    *,
    division: str | None = None,
    jurisdiction: str | None = None,
    population: str | None = None,
    max_age_days: int | None = None,
    as_of: datetime | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Retrieve approved documents matching scope and freshness requirements.

    Scope fields are read from document metadata. When a caller requests a
    scope, missing metadata is excluded rather than treated as a wildcard.
    Freshness is enforced only when max_age_days is supplied; in that case a
    missing/invalid retrieved_at value is excluded.
    """
    for name, value in (("division", division), ("jurisdiction", jurisdiction), ("population", population)):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{name} must be a non-empty string when supplied.")
    if max_age_days is not None and (
        isinstance(max_age_days, bool) or not isinstance(max_age_days, int) or max_age_days < 0
    ):
        raise ValueError("max_age_days must be a non-negative integer.")
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("as_of must include a timezone.")
    now = now.astimezone(timezone.utc)

    candidates = retrieve(query, limit=50)
    scoped: list[dict[str, Any]] = []
    for item in candidates:
        try:
            metadata = json.loads(item.get("metadata_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(metadata, dict):
            continue
        # Bundled material uses "collection" as its division label.
        actual_division = metadata.get("division", metadata.get("collection"))
        if division is not None and actual_division != division:
            continue
        if jurisdiction is not None and metadata.get("jurisdiction") != jurisdiction:
            continue
        if population is not None and metadata.get("population") != population:
            continue
        expiry = metadata.get("expiry_at") or metadata.get("expires_at")
        if expiry is not None:
            try:
                if _parse_timestamp(expiry, "expiry_at") <= now:
                    continue
            except ValueError:
                continue
        if max_age_days is not None:
            retrieved = metadata.get("retrieved_at") or metadata.get("retrieved")
            try:
                retrieved_at = _parse_timestamp(retrieved, "retrieved_at")
            except ValueError:
                continue
            if retrieved_at > now or now - retrieved_at > timedelta(days=max_age_days):
                continue
        scoped.append(item)
        if len(scoped) >= limit:
            break
    return scoped
