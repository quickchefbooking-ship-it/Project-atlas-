"""Deterministic, source-linked reports from evaluated evidence.

The report formats prior classifications; it does not create new factual
conclusions or strengthen the underlying evidence.
"""
from __future__ import annotations

from typing import Any

MAX_SOURCES = 20
MAX_EVALUATIONS = 400
_STATUSES = {
    "supported_by_supplied_annotations",
    "challenged_by_supplied_annotations",
    "conflicting_annotations",
    "insufficient_evidence",
}


def build_professor_report(bundle: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    """Create a bounded report with traceable source records and explicit gaps."""
    if not isinstance(bundle, dict) or bundle.get("schema_version") != 1:
        raise ValueError("A schema version 1 evidence bundle is required.")
    if not isinstance(evaluation, dict) or evaluation.get("schema_version") != 1:
        raise ValueError("A schema version 1 evaluation is required.")
    sources = bundle.get("sources")
    evaluated = evaluation.get("evaluations")
    if not isinstance(sources, list) or len(sources) > MAX_SOURCES:
        raise ValueError("Report source records are invalid or exceed the limit.")
    if not isinstance(evaluated, list) or len(evaluated) > MAX_EVALUATIONS:
        raise ValueError("Report evaluations are invalid or exceed the limit.")

    source_map: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("Report contains an invalid source record.")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id or source_id in source_map:
            raise ValueError("Report source identifiers must be unique.")
        source_map[source_id] = {
            "source_id": source_id,
            "title": source.get("title", ""),
            "uri": source.get("uri", ""),
            "doi": source.get("doi", ""),
            "publisher": source.get("publisher", ""),
            "retrieved_at": source.get("retrieved_at", ""),
        }

    groups = {
        "findings": [],
        "challenges": [],
        "disagreements": [],
        "evidence_gaps": [],
    }
    for item in evaluated:
        if not isinstance(item, dict) or item.get("status") not in _STATUSES:
            raise ValueError("Report contains an unsupported evaluation status.")
        refs: list[str] = []
        for field in ("supporting_source_ids", "challenging_source_ids", "mentioning_source_ids"):
            ids = item.get(field, [])
            if not isinstance(ids, list):
                raise ValueError("Evaluation source references must be lists.")
            for source_id in ids:
                if source_id not in source_map:
                    raise ValueError("Evaluation references a source absent from its evidence bundle.")
                if source_id not in refs:
                    refs.append(source_id)
        status = item["status"]
        record = {
            "claim_id": item.get("claim_id"),
            "claim": item.get("text"),
            "status": status,
            "supporting_sources": [source_id for source_id in item.get("supporting_source_ids", [])],
            "challenging_sources": [source_id for source_id in item.get("challenging_source_ids", [])],
            "mentioning_sources": [source_id for source_id in item.get("mentioning_source_ids", [])],
            "source_references": refs,
            "annotation_audit": item.get("annotation_audit", []),
            "confidence": "not_scored",
            "interpretation": item.get("interpretation", ""),
        }
        if status == "supported_by_supplied_annotations":
            groups["findings"].append(record)
        elif status == "challenged_by_supplied_annotations":
            groups["challenges"].append(record)
        elif status == "conflicting_annotations":
            groups["disagreements"].append(record)
        else:
            groups["evidence_gaps"].append(record)

    limitations = []
    for origin in (bundle.get("limitations", []), evaluation.get("limitations", [])):
        if not isinstance(origin, list):
            raise ValueError("Report limitations must be lists.")
        for limitation in origin:
            if isinstance(limitation, str) and limitation and limitation not in limitations:
                limitations.append(limitation)
    if not limitations:
        limitations.append("This report organises supplied annotations and does not independently verify claims.")

    duplicate_records = bundle.get("duplicate_records", [])
    if not isinstance(duplicate_records, list):
        raise ValueError("Report duplicate records are invalid.")
    return {
        "schema_version": 1,
        "report_type": "professor_evidence_report",
        "title": "Evidence review report",
        "executive_summary": {
            "claim_count": len(evaluated),
            "finding_count": len(groups["findings"]),
            "challenge_count": len(groups["challenges"]),
            "disagreement_count": len(groups["disagreements"]),
            "evidence_gap_count": len(groups["evidence_gaps"]),
            "source_count": len(source_map),
            "duplicate_record_group_count": len(duplicate_records),
            "confidence": "not_scored",
            "overall_conclusion": "No overall truth conclusion is drawn from annotation labels alone.",
        },
        **groups,
        "sources": list(source_map.values()),
        "duplicate_records": duplicate_records,
        "limitations": limitations,
        "review_note": "Source references identify records in the supplied bundle. Review the original sources before relying on any claim.",
    }
