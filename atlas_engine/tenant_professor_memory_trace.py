"""Opt-in, privacy-bounded retrieval explanation helper.

This helper explains returned candidates only. It does not log queries or memory
content, and it is not wired into the reasoning pipeline by default.
"""
from __future__ import annotations

from typing import Any

TRACE_VERSION = "professor-memory-retrieval-trace-v1"


def explain_memory_retrieval(repository: Any, query: str, *, limit: int = 5) -> dict:
    """Return a bounded trace of candidates returned by an authorized repository.

    Repository.retrieve remains the authority for access control, approval,
    expiry, supersession, scoring, and ranking. This wrapper deliberately does
    not include the full query, candidate content, or hidden records.
    """
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")

    candidates = repository.retrieve(query, limit=limit)
    trace_candidates = []
    for rank, candidate in enumerate(candidates, start=1):
        matched_terms = candidate.get("matched_terms", [])
        matched_fields = candidate.get("matched_fields", [])
        trace_candidates.append({
            "proposal_id": candidate["proposal_id"],
            "rank": rank,
            "matched_terms": sorted(set(matched_terms)),
            "matched_fields": sorted(set(matched_fields)),
            "synonym_expansion_contributed": bool(matched_terms)
                and not any(field for field in matched_fields),
        })

    return {
        "trace_version": TRACE_VERSION,
        "candidate_count": len(trace_candidates),
        "limit": limit,
        "candidates": trace_candidates,
    }
