"""Explicit human review annotations with immutable reviewer attribution.

This layer accepts labels only from a caller that has already authenticated and
authorized the reviewer. It never extracts claims or assigns relations itself.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

MAX_ANNOTATIONS = 400
_RELATIONS = {"supports", "challenges", "mentions"}


def apply_reviewer_annotations(
    bundle: dict[str, Any],
    annotations: list[dict[str, Any]],
    *,
    reviewer_id: str,
    reviewed_at: str,
) -> dict[str, Any]:
    """Return a validated copy of a bundle with explicitly supplied annotations."""
    if not isinstance(bundle, dict) or bundle.get("schema_version") != 1:
        raise ValueError("A schema version 1 evidence bundle is required.")
    if not isinstance(annotations, list) or not 1 <= len(annotations) <= MAX_ANNOTATIONS:
        raise ValueError(f"Provide between 1 and {MAX_ANNOTATIONS} reviewer annotations.")
    if not isinstance(reviewer_id, str) or not reviewer_id.strip() or len(reviewer_id) > 128:
        raise ValueError("reviewer_id must be non-empty and at most 128 characters.")
    if not isinstance(reviewed_at, str) or not reviewed_at.strip() or len(reviewed_at) > 64:
        raise ValueError("reviewed_at must be a non-empty timestamp of at most 64 characters.")

    result = deepcopy(bundle)
    sources = result.get("sources")
    claims = result.get("claims")
    if not isinstance(sources, list) or not isinstance(claims, list):
        raise ValueError("Evidence bundle source and claim lists are required.")
    source_ids = {
        source.get("source_id") for source in sources if isinstance(source, dict)
    }
    claim_map = {}
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError("Evidence bundle contains an invalid claim.")
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id or claim_id in claim_map:
            raise ValueError("Evidence bundle claim identifiers must be unique.")
        if not isinstance(claim.get("text"), str) or not claim["text"].strip():
            raise ValueError("Evidence bundle claim text is required.")
        if not isinstance(claim.get("annotations"), list):
            raise ValueError("Evidence bundle claim annotations must be a list.")
        claim_map[claim_id] = claim

    seen = set()
    for item in annotations:
        if not isinstance(item, dict) or set(item) != {"claim_id", "text", "source_id", "relation"}:
            raise ValueError("Each reviewer annotation requires claim_id, text, source_id and relation only.")
        claim_id, text, source_id, relation = (
            item["claim_id"], item["text"], item["source_id"], item["relation"]
        )
        if not isinstance(claim_id, str) or not claim_id.strip() or len(claim_id) > 120:
            raise ValueError("claim_id is invalid.")
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise ValueError("Claim text is invalid.")
        if source_id not in source_ids:
            raise ValueError("Reviewer annotation references an unknown source.")
        if relation not in _RELATIONS:
            raise ValueError("Reviewer relation must be supports, challenges or mentions.")
        key = (claim_id, source_id, relation)
        if key in seen:
            raise ValueError("Duplicate reviewer annotation in one submission.")
        seen.add(key)

        claim = claim_map.get(claim_id)
        if claim is None:
            claim = {"claim_id": claim_id, "text": text.strip(), "annotations": []}
            claim_map[claim_id] = claim
            claims.append(claim)
        elif claim["text"].casefold() != text.strip().casefold():
            raise ValueError("A claim_id must refer to one consistent claim text.")
        if any(
            existing.get("source_id") == source_id and existing.get("relation") == relation
            for existing in claim["annotations"]
        ):
            raise ValueError("This source relation is already annotated for the claim.")
        claim["annotations"].append({
            "source_id": source_id,
            "relation": relation,
            "reviewer_id": reviewer_id.strip(),
            "reviewed_at": reviewed_at.strip(),
        })

    if len(claims) > 400:
        raise ValueError("Evidence bundle exceeds the 400-claim limit.")
    result["claims"] = claims
    result["summary"] = dict(result.get("summary") or {})
    result["summary"]["claim_count"] = len(claims)
    result["summary"]["confidence"] = "not_scored"
    result["limitations"] = list(result.get("limitations") or [])
    result["limitations"].append(
        "Reviewer labels record human-supplied interpretations; they do not independently establish claim truth."
    )
    return result
