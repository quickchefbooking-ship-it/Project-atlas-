"""Deterministic evidence bundling with explicit provenance and uncertainty.

This module organises researcher-supplied claim annotations; it does not infer
claims from abstracts, judge truth, or treat source count as proof.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

MAX_SOURCES = 20
MAX_CLAIMS_PER_SOURCE = 20
MAX_TEXT = 2000
_RELATIONS = {"supports", "challenges", "mentions"}


def _text(value: Any, field: str, maximum: int = MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field} must be non-empty text of at most {maximum} characters.")
    return value.strip()


def _source_id(source: dict[str, Any]) -> str:
    uri = _text(source.get("uri"), "source.uri", 1000)
    parsed = urlparse(uri)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Source URI must be an absolute HTTP(S) URL without credentials.")
    doi = source.get("doi")
    if doi is not None:
        doi = _text(doi, "source.doi", 200).lower()
        return "doi:" + doi
    return "uri:" + uri.rstrip("/").lower()


def build_evidence_bundle(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a bounded, auditable bundle from explicitly annotated source claims.

    Input relation labels are annotations, not automated assessments. Conflicts
    mean only that supplied annotations differ for the same explicit claim_id.
    """
    if not isinstance(sources, list) or not 1 <= len(sources) <= MAX_SOURCES:
        raise ValueError(f"Provide between 1 and {MAX_SOURCES} source records.")
    source_index: dict[str, dict[str, Any]] = {}
    duplicate_groups: dict[str, list[str]] = defaultdict(list)
    claim_groups: dict[str, dict[str, Any]] = {}

    for index, raw in enumerate(sources):
        if not isinstance(raw, dict) or set(raw) - {"title", "uri", "doi", "publisher", "retrieved_at", "claims"}:
            raise ValueError("Source records contain unsupported fields.")
        title = _text(raw.get("title"), "source.title", 500)
        uri = _text(raw.get("uri"), "source.uri", 1000)
        sid = _source_id(raw)
        duplicate_groups[sid].append(f"source-{index + 1}")
        source_index[f"source-{index + 1}"] = {
            "source_id": f"source-{index + 1}",
            "title": title,
            "uri": uri,
            "doi": str(raw.get("doi") or "")[:200],
            "publisher": str(raw.get("publisher") or "")[:300],
            "retrieved_at": str(raw.get("retrieved_at") or "")[:64],
        }
        claims = raw.get("claims", [])
        if not isinstance(claims, list) or len(claims) > MAX_CLAIMS_PER_SOURCE:
            raise ValueError(f"Each source may contain at most {MAX_CLAIMS_PER_SOURCE} annotated claims.")
        for annotation in claims:
            if not isinstance(annotation, dict) or set(annotation) != {"claim_id", "text", "relation"}:
                raise ValueError("Each claim annotation requires claim_id, text and relation only.")
            claim_id = _text(annotation["claim_id"], "claim_id", 120)
            claim_text = _text(annotation["text"], "claim.text")
            relation = annotation["relation"]
            if relation not in _RELATIONS:
                raise ValueError("Claim relation must be supports, challenges or mentions.")
            entry = claim_groups.setdefault(claim_id, {
                "claim_id": claim_id, "text": claim_text, "annotations": [],
            })
            if entry["text"].casefold() != claim_text.casefold():
                raise ValueError("A claim_id must refer to one consistent claim text.")
            entry["annotations"].append({
                "source_id": f"source-{index + 1}", "relation": relation,
            })

    duplicates = [
        {"source_key": key, "source_ids": ids, "notice": "Records share a DOI or canonical URI; this is a duplicate-record signal, not independent corroboration."}
        for key, ids in sorted(duplicate_groups.items()) if len(ids) > 1
    ]
    claims = []
    for claim_id, entry in sorted(claim_groups.items()):
        relations = {item["relation"] for item in entry["annotations"]}
        conflicts = "supports" in relations and "challenges" in relations
        claims.append({
            "claim_id": claim_id,
            "text": entry["text"],
            "annotations": entry["annotations"],
            "assessment": "conflicting_annotations" if conflicts else (
                "supporting_annotations_only" if "supports" in relations else
                "challenging_annotations_only" if "challenges" in relations else
                "mentions_only"
            ),
            "uncertainty": "Annotation-based grouping only; source quality, methods, context and truth have not been independently assessed.",
        })
    return {
        "schema_version": 1,
        "sources": list(source_index.values()),
        "claims": claims,
        "duplicate_records": duplicates,
        "summary": {
            "source_count": len(source_index),
            "claim_count": len(claims),
            "duplicate_group_count": len(duplicates),
            "conflicting_claim_count": sum(item["assessment"] == "conflicting_annotations" for item in claims),
            "confidence": "not_scored",
        },
        "limitations": [
            "Claims and relation labels must be supplied by a reviewer or a separately validated extractor.",
            "Different annotations do not establish that sources disagree on the underlying facts.",
            "Duplicate records are not independent evidence.",
            "No source credibility, methodology, causal validity or factual truth assessment is performed.",
        ],
    }
