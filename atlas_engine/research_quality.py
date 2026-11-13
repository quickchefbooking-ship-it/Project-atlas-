"""Deterministic, transparent evidence-quality diagnostics for Professor reports.

These diagnostics describe observable report structure and provenance metadata.
They are not a truth score and do not determine whether evidence semantically
supports a claim.
"""
from __future__ import annotations

from .research_evidence import ResearchReport


def assess_evidence_quality(report: ResearchReport) -> dict:
    """Return per-dimension diagnostics without collapsing them into a score."""
    if not isinstance(report, ResearchReport):
        raise TypeError("A validated ResearchReport is required.")

    evidence_by_id = {item.evidence_id: item for item in report.evidence}
    cited_ids = {
        evidence_id
        for claim in report.claims
        for evidence_id in claim.evidence_ids
    }
    cited = [evidence_by_id[item] for item in sorted(cited_ids)]
    source_ids = {item.source_id for item in cited}
    unused_ids = sorted(set(evidence_by_id) - cited_ids)
    pending_ids = sorted(
        item.evidence_id for item in cited
        if item.review_state == "pending"
    )
    rejected_ids = sorted(
        item.evidence_id for item in cited
        if item.review_state == "rejected"
    )
    unverified_ids = sorted(
        item.evidence_id for item in cited
        if item.trust_level == "unverified"
    )
    claim_status_counts = {
        status: sum(claim.status == status for claim in report.claims)
        for status in ("supported", "provisional", "disputed", "unknown")
    }
    conflicted_claim_ids = sorted({
        claim_id
        for conflict in report.conflicts
        for claim_id in (conflict.claim_a, conflict.claim_b)
    })

    dimensions = {
        "provenance": {
            "report_evidence_count": len(report.evidence),
            "cited_evidence_count": len(cited),
            "uncited_evidence_ids": unused_ids,
            "status": "complete" if not unused_ids else "partial",
        },
        "source_diversity": {
            "distinct_cited_source_count": len(source_ids),
            "status": (
                "no_cited_sources" if not source_ids
                else "single_source" if len(source_ids) == 1
                else "multiple_sources"
            ),
        },
        "review_state": {
            "pending_evidence_ids": pending_ids,
            "rejected_evidence_ids": rejected_ids,
            "unverified_evidence_ids": unverified_ids,
            "status": (
                "rejected_evidence_present" if rejected_ids
                else "pending_or_unverified" if pending_ids or unverified_ids
                else "approved_metadata"
            ),
        },
        "citation_completeness": {
            "claim_count": len(report.claims),
            "claims_with_citations": sum(bool(claim.evidence_ids) for claim in report.claims),
            "claim_status_counts": claim_status_counts,
            "status": "all_claims_cited",
        },
        "conflicts": {
            "conflict_count": len(report.conflicts),
            "conflicted_claim_ids": conflicted_claim_ids,
            "status": "conflicts_recorded" if report.conflicts else "none_recorded",
        },
        "uncertainty_and_limitations": {
            "uncertainty_count": len(report.uncertainty),
            "limitation_count": len(report.limitations),
            "status": (
                "documented" if report.uncertainty and report.limitations
                else "partially_documented" if report.uncertainty or report.limitations
                else "not_documented"
            ),
        },
    }

    warnings = []
    if unused_ids:
        warnings.append("One or more report evidence items are not cited by any claim.")
    if len(source_ids) == 1:
        warnings.append("All cited evidence comes from one distinct source.")
    elif not source_ids:
        warnings.append("No evidence is cited by the report claims.")
    if pending_ids:
        warnings.append("One or more cited sources remain pending review.")
    if rejected_ids:
        warnings.append("One or more cited sources have been rejected.")
    if unverified_ids:
        warnings.append("One or more cited sources have unverified trust metadata.")
    if report.conflicts:
        warnings.append("The report records claim conflicts that require resolution or explanation.")
    if not report.uncertainty:
        warnings.append("The report does not record uncertainty.")
    if not report.limitations:
        warnings.append("The report does not record limitations.")
    if claim_status_counts["unknown"] or claim_status_counts["disputed"]:
        warnings.append("The report contains disputed or unknown claims.")

    return {
        "schema_version": "1.0",
        "dimensions": dimensions,
        "warnings": warnings,
        "quality_score": None,
        "truth_assessed": False,
        "semantic_support_assessed": False,
    }
