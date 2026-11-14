"""Transparent evaluation of reviewer-annotated evidence bundles.

This module classifies the supplied annotations. It does not infer claim truth,
rank journals, inspect methods, or calculate confidence.
"""
from __future__ import annotations

from typing import Any

MAX_SOURCES = 20
MAX_CLAIMS = 400
_RELATIONS = {"supports", "challenges", "mentions"}


def evaluate_evidence_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Classify each claim from its explicit annotations and preserve provenance."""
    if not isinstance(bundle, dict) or bundle.get("schema_version") != 1:
        raise ValueError("A schema version 1 evidence bundle is required.")
    sources = bundle.get("sources")
    claims = bundle.get("claims")
    duplicates = bundle.get("duplicate_records")
    if not isinstance(sources, list) or len(sources) > MAX_SOURCES:
        raise ValueError("Evidence bundle sources are invalid or exceed the limit.")
    if not isinstance(claims, list) or len(claims) > MAX_CLAIMS:
        raise ValueError("Evidence bundle claims are invalid or exceed the limit.")
    if not isinstance(duplicates, list):
        raise ValueError("Evidence bundle duplicate records are invalid.")

    source_ids = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("Evidence bundle contains an invalid source.")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id or source_id in source_ids:
            raise ValueError("Evidence bundle source identifiers must be unique.")
        source_ids.add(source_id)

    # Treat each duplicate group as one record when counting independent
    # annotated records. This is not a judgement of scientific independence.
    duplicate_owner: dict[str, str] = {}
    for index, group in enumerate(duplicates):
        if not isinstance(group, dict) or not isinstance(group.get("source_ids"), list):
            raise ValueError("Evidence bundle contains an invalid duplicate group.")
        owner = f"duplicate-group-{index + 1}"
        for source_id in group["source_ids"]:
            if source_id not in source_ids or source_id in duplicate_owner:
                raise ValueError("Duplicate groups contain unknown or repeated source identifiers.")
            duplicate_owner[source_id] = owner

    evaluated = []
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get("annotations"), list):
            raise ValueError("Evidence bundle contains an invalid claim.")
        relations = set()
        supporting, challenging, mentioning = [], [], []
        for annotation in claim["annotations"]:
            if not isinstance(annotation, dict):
                raise ValueError("Claim annotation is invalid.")
            source_id, relation = annotation.get("source_id"), annotation.get("relation")
            if source_id not in source_ids or relation not in _RELATIONS:
                raise ValueError("Claim annotation has an unknown source or relation.")
            relations.add(relation)
            target = supporting if relation == "supports" else challenging if relation == "challenges" else mentioning
            target.append(source_id)

        if "supports" in relations and "challenges" in relations:
            status = "conflicting_annotations"
        elif "supports" in relations:
            status = "supported_by_supplied_annotations"
        elif "challenges" in relations:
            status = "challenged_by_supplied_annotations"
        else:
            status = "insufficient_evidence"

        annotated_ids = supporting + challenging + mentioning
        independent_groups = {
            duplicate_owner.get(source_id, source_id) for source_id in annotated_ids
        }
        evaluated.append({
            "claim_id": claim.get("claim_id"),
            "text": claim.get("text"),
            "status": status,
            "supporting_source_ids": supporting,
            "challenging_source_ids": challenging,
            "mentioning_source_ids": mentioning,
            "annotated_source_count": len(set(annotated_ids)),
            "distinct_record_group_count": len(independent_groups),
            "confidence": "not_scored",
            "interpretation": (
                "Classification reflects supplied relation labels only; it is not a finding that the claim is true or false."
            ),
        })

    counts = {key: sum(item["status"] == key for item in evaluated) for key in (
        "supported_by_supplied_annotations", "challenged_by_supplied_annotations",
        "conflicting_annotations", "insufficient_evidence",
    )}
    return {
        "schema_version": 1,
        "evaluations": evaluated,
        "summary": {
            "claim_count": len(evaluated),
            **counts,
            "confidence": "not_scored",
            "duplicate_groups_treated_as_single_record_groups": len(duplicates),
        },
        "limitations": [
            "Statuses classify reviewer-supplied annotations; no claim is independently verified.",
            "No source credibility, study design, sample size, bias, causality or recency assessment is performed.",
            "Duplicate DOI or URI records are grouped and must not be counted as separate corroboration.",
            "A supported or challenged annotation is not a calibrated probability or confidence score.",
        ],
    }
