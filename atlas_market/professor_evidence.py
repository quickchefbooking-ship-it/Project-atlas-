"""Professor evidence bridge for Atlas Market Intelligence."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence
from atlas_engine.learning_memory import LearningMemory
from .market_data import WatchlistItem

MAX_EVIDENCE_BYTES = 12 * 1024
MARKET_LESSON_TYPES = {
    "market_verified",
    "market_failed",
    "market_partial",
    "market_uncertain",
}

class ProfessorEvidenceError(ValueError):
    """Unsafe or invalid Professor evidence."""

def _json_safe(value: Any, depth: int = 0) -> Any:
    if depth > 16:
        raise ProfessorEvidenceError("Evidence nesting exceeds supported limit")
    if value is None or type(value) in (str, bool, int):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ProfessorEvidenceError("Non-finite decimal")
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ProfessorEvidenceError("Timestamps must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Mapping):
        if any(not isinstance(k, str) for k in value):
            raise ProfessorEvidenceError("Evidence keys must be strings")
        return {k: _json_safe(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v, depth + 1) for v in value]
    raise ProfessorEvidenceError("Evidence contains an unsupported value")

def record_market_observation(*, task_id: str, summary: str, outcome: str,
                              source: str, evidence: Mapping[str, Any],
                              observed_at: datetime | None = None) -> dict[str, Any]:
    """Store one bounded outcome as an unvalidated lesson."""
    if outcome not in {"verified", "failed", "partial", "uncertain"}:
        raise ProfessorEvidenceError("Unsupported outcome")
    timestamp = observed_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ProfessorEvidenceError("observed_at must be timezone-aware")
    timestamp = timestamp.astimezone(timezone.utc)
    safe_evidence = _json_safe(dict(evidence))
    envelope = {"domain":"atlas_market_intelligence","outcome":outcome,
                "observed_at":timestamp.isoformat(),"source":source,
                "evidence":safe_evidence}
    canonical = json.dumps(envelope, sort_keys=True, separators=(",",":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    envelope["evidence_sha256"] = digest
    encoded = json.dumps(envelope, sort_keys=True, separators=(",",":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_EVIDENCE_BYTES:
        raise ProfessorEvidenceError("Market evidence exceeds bounded record size")
    lesson = LearningMemory.save_lesson_for_task(
        task_id=task_id, lesson_type=f"market_{outcome}", summary=summary,
        source=source, evidence=envelope, validated=False)
    return {"lesson_id":lesson["id"],"task_id":task_id,
            "domain":"atlas_market_intelligence","outcome":outcome,
            "observed_at":timestamp.isoformat(),"evidence_sha256":digest,
            "validated":False,"guidance_eligible":False}

def record_watchlist_evidence(*, task_id: str, items: Sequence[WatchlistItem],
                              summary: str = "Synthetic market watchlist fixture validated") -> dict[str, Any]:
    """Record fixture provenance and claim scope, not raw time-series data."""
    evidence_items = [{
        "instrument_id":item.instrument.instrument_id,
        "asset_class":item.instrument.asset_class,"venue":item.instrument.venue,
        "availability":item.availability,"data_status":item.data_status,
        "source_id":item.source_id,"source_version":item.source_version,
        "interval":item.interval,"last_bar_end":item.last_bar_end,
        "last_observed_at":item.last_observed_at,
        "chart_point_count":len(item.chart_points)} for item in items]
    return record_market_observation(
        task_id=task_id,summary=summary,outcome="verified",
        source="atlas_market.synthetic_watchlist",
        evidence={"mode":"synthetic","items":evidence_items,
                  "claim_scope":"deterministic fixture projection only; not real market observations"})

def get_professor_market_guidance(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Return only owner-validated lessons explicitly belonging to Market Intelligence."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError("Market guidance limit must be between 1 and 50.")
    if not isinstance(query, str) or not query.strip():
        return []

    # Search a broad candidate set first, then enforce the market-domain boundary.
    # LearningMemory already returns only owner-validated lessons.
    lessons = LearningMemory.get_relevant_lessons(
        f"atlas market intelligence {query}", limit=50)
    guidance: list[dict[str, Any]] = []
    for item in lessons:
        if item.get("lesson_type") not in MARKET_LESSON_TYPES:
            continue
        try:
            evidence = json.loads(item.get("evidence_json") or "")
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(evidence, dict):
            continue
        if evidence.get("domain") != "atlas_market_intelligence":
            continue
        if evidence.get("outcome") != item["lesson_type"].removeprefix("market_"):
            continue
        guidance.append({
            "lesson_id":item.get("id"),"summary":item.get("summary"),
            "source":item.get("source"),"created_at":item.get("created_at"),
            "evidence_json":item.get("evidence_json"),"trust":"owner_validated",
            "mode":"advisory_only","executable":False})
        if len(guidance) >= limit:
            break
    return guidance
