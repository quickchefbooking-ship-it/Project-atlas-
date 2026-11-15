"""Evidence-linked research report contract and deterministic integrity checks.

This module validates traceability and provenance metadata only. It does not decide
whether a source semantically supports a claim or whether a conclusion is true.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResearchEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    evidence_id: str = Field(min_length=1, max_length=160)
    source_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=500)
    uri: str = Field(min_length=1, max_length=2048)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    trust_level: Literal["unverified", "reviewed", "authoritative"]
    review_state: Literal["pending", "approved", "rejected"]
    retrieved_at: str = Field(min_length=1, max_length=64)
    published_at: str | None = Field(default=None, max_length=64)


class ResearchClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    claim_id: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=2_000)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)
    status: Literal["supported", "provisional", "disputed", "unknown"]
    confidence: float = Field(ge=0.0, le=1.0)


class ClaimConflict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    claim_a: str = Field(min_length=1, max_length=128)
    claim_b: str = Field(min_length=1, max_length=128)
    explanation: str = Field(min_length=1, max_length=1_000)


class ResearchReport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["1.0"] = "1.0"
    task_id: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=4_000)
    recommendation: str = Field(min_length=1, max_length=4_000)
    claims: list[ResearchClaim] = Field(min_length=1, max_length=100)
    evidence: list[ResearchEvidence] = Field(min_length=1, max_length=200)
    conflicts: list[ClaimConflict] = Field(default_factory=list, max_length=100)
    uncertainty: list[str] = Field(default_factory=list, max_length=30)
    limitations: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_traceability(self):
        claim_ids = [claim.claim_id for claim in self.claims]
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("Claim IDs must be unique.")
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Evidence IDs must be unique.")

        evidence_by_id = {item.evidence_id: item for item in self.evidence}
        for claim in self.claims:
            if len(claim.evidence_ids) != len(set(claim.evidence_ids)):
                raise ValueError("A claim cannot cite the same evidence more than once.")
            missing = set(claim.evidence_ids) - evidence_by_id.keys()
            if missing:
                raise ValueError("Every claim citation must resolve to report evidence.")
            if claim.status == "supported":
                cited = [evidence_by_id[item] for item in claim.evidence_ids]
                if not any(
                    item.review_state == "approved"
                    and item.trust_level in {"reviewed", "authoritative"}
                    for item in cited
                ):
                    raise ValueError(
                        "A supported claim requires at least one approved reviewed or authoritative source."
                    )

        for conflict in self.conflicts:
            if conflict.claim_a == conflict.claim_b:
                raise ValueError("A claim cannot conflict with itself.")
            if conflict.claim_a not in claim_ids or conflict.claim_b not in claim_ids:
                raise ValueError("Conflict references must resolve to report claims.")
        return self


def assess_report_integrity(report: ResearchReport) -> dict:
    """Return deterministic traceability metrics, not a truth or quality score."""
    if not isinstance(report, ResearchReport):
        raise TypeError("A validated ResearchReport is required.")

    cited_ids = {
        evidence_id
        for claim in report.claims
        for evidence_id in claim.evidence_ids
    }
    cited_evidence = [item for item in report.evidence if item.evidence_id in cited_ids]
    source_ids = {item.source_id for item in cited_evidence}
    pending_citations = [
        item.evidence_id for item in cited_evidence
        if item.review_state != "approved"
        or item.trust_level == "unverified"
    ]
    warnings = []
    if len(source_ids) < 2:
        warnings.append("Fewer than two distinct sources are cited.")
    if pending_citations:
        warnings.append("One or more cited sources remain pending or unverified.")
    if not report.uncertainty:
        warnings.append("The report does not record any uncertainty.")
    if not report.limitations:
        warnings.append("The report does not record any limitations.")

    return {
        "claim_count": len(report.claims),
        "evidence_count": len(report.evidence),
        "cited_evidence_count": len(cited_evidence),
        "distinct_cited_source_count": len(source_ids),
        "conflict_count": len(report.conflicts),
        "pending_or_unverified_evidence_ids": pending_citations,
        "warnings": warnings,
        "truth_assessed": False,
        "semantic_support_assessed": False,
    }
