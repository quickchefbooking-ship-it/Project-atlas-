"""Deterministic question answering over a completed Professor evidence report.

This is a deliberately bounded first conversational layer: it retrieves and
summarises report fields only. It does not infer truth, follow source text as
instructions, call a model, invoke tools, or perform actions.
"""
from __future__ import annotations

import re
from typing import Any

MAX_QUESTION_CHARS = 1000
_SECTIONS = (
    ("findings", "findings"),
    ("challenges", "challenges"),
    ("disagreements", "disagreements"),
    ("evidence_gaps", "evidence gaps"),
)


def answer_report_question(report: dict[str, Any], question: str) -> dict[str, Any]:
    """Answer common report questions using only validated report structure."""
    if not isinstance(report, dict) or report.get("report_type") != "professor_evidence_report":
        raise ValueError("A completed Professor evidence report is required.")
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_CHARS:
        raise ValueError("Question must contain 1 to 1000 characters.")

    summary = report.get("executive_summary")
    if not isinstance(summary, dict):
        raise ValueError("The report summary is invalid.")
    q = question.casefold()
    sources = report.get("sources", [])
    if not isinstance(sources, list):
        sources = []

    def items_for(key: str) -> list[dict[str, Any]]:
        value = report.get(key, [])
        return value if isinstance(value, list) else []

    if any(term in q for term in ("source", "reference", "doi", "publisher")):
        safe_sources = [
            {k: source.get(k, "") for k in ("source_id", "title", "doi", "publisher", "uri")}
            for source in sources if isinstance(source, dict)
        ]
        return {
            "answer": f"The report contains {len(safe_sources)} source record(s). These are references supplied to the report, not independently verified endorsements.",
            "basis": "source_register",
            "sources": safe_sources[:20],
            "limitations": report.get("limitations", []),
        }

    matched = None
    for key, label in _SECTIONS:
        if any(term in q for term in (key.replace("_", " "), label)):
            matched = (key, label)
            break
    if matched:
        key, label = matched
        records = items_for(key)
        return {
            "answer": f"The report records {len(records)} {label}.",
            "basis": key,
            "items": [
                {
                    "claim_id": item.get("claim_id"),
                    "claim": item.get("claim"),
                    "status": item.get("status"),
                    "supporting_sources": item.get("supporting_sources", []),
                    "challenging_sources": item.get("challenging_sources", []),
                    "source_references": item.get("source_references", []),
                    "interpretation": item.get("interpretation", ""),
                }
                for item in records[:50] if isinstance(item, dict)
            ],
        }

    if any(term in q for term in ("overall", "conclusion", "bottom line", "summary", "how many", "count")):
        return {
            "answer": (
                f"The report covers {summary.get('claim_count', 0)} claim(s): "
                f"{summary.get('finding_count', 0)} findings, "
                f"{summary.get('challenge_count', 0)} challenges, "
                f"{summary.get('disagreement_count', 0)} disagreements and "
                f"{summary.get('evidence_gap_count', 0)} evidence gaps, "
                f"across {summary.get('source_count', 0)} source record(s). "
                "Confidence is not scored. No overall truth conclusion is drawn from annotation labels alone."
            ),
            "basis": "executive_summary",
            "limitations": report.get("limitations", []),
        }

    # For a specific claim, return only exact lexical matches from claim text.
    terms = {word for word in re.findall(r"[a-z0-9]{3,}", q) if word not in {"what", "with", "does", "this", "that", "from", "about", "tell", "show", "report"}}
    candidates = []
    for key, _label in _SECTIONS:
        for item in items_for(key):
            if not isinstance(item, dict):
                continue
            claim = item.get("claim", "")
            if not isinstance(claim, str):
                continue
            claim_terms = set(re.findall(r"[a-z0-9]{3,}", claim.casefold()))
            overlap = len(terms & claim_terms)
            if overlap:
                candidates.append((overlap, item))
    candidates.sort(key=lambda pair: (-pair[0], str(pair[1].get("claim_id", ""))))
    if candidates:
        records = []
        for _score, item in candidates[:10]:
            records.append({
                "claim_id": item.get("claim_id"),
                "claim": item.get("claim"),
                "status": item.get("status"),
                "supporting_sources": item.get("supporting_sources", []),
                "challenging_sources": item.get("challenging_sources", []),
                "source_references": item.get("source_references", []),
                "interpretation": item.get("interpretation", ""),
            })
        return {
            "answer": f"I found {len(records)} report item(s) matching your wording. These are report annotations, not independently verified facts.",
            "basis": "lexical_claim_match",
            "items": records,
            "limitations": report.get("limitations", []),
        }

    return {
        "answer": "I can't answer that from this report alone. Try asking about its summary, findings, challenges, disagreements, evidence gaps or sources.",
        "basis": "insufficient_report_context",
        "items": [],
        "limitations": report.get("limitations", []),
    }
