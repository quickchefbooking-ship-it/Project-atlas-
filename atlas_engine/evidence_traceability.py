"""Traceability checks for reviewer-annotated evidence excerpts.

This module verifies that a supplied excerpt occurs in a supplied source
snapshot and binds the review record to that snapshot's digest. It does not
decide whether the excerpt supports a claim or whether the source is credible.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

MAX_SOURCE_TEXT_CHARS = 1_000_000
MAX_EXCERPT_CHARS = 2_000
MAX_CLAIM_CHARS = 2_000
MAX_LOCATOR_CHARS = 500
MAX_REVIEWER_ID_CHARS = 128
_RELATIONS = {"supports", "challenges", "mentions"}


def _required_text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field} must be non-empty text of at most {maximum} characters.")
    return value.strip()


def _source_uri(value: Any) -> str:
    uri = _required_text(value, "source_uri", 2_000)
    parsed = urlparse(uri)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
    ):
        raise ValueError("source_uri must be an absolute HTTPS URI without credentials or alternate ports.")
    return uri


def _review_timestamp(value: Any) -> str:
    timestamp = _required_text(value, "reviewed_at", 64)
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("reviewed_at must be an ISO-8601 timestamp with timezone.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("reviewed_at must include a timezone.")
    return timestamp


def verify_evidence_excerpt(
    *,
    source_uri: str,
    source_text: str,
    excerpt: str,
    locator: str,
    claim_id: str,
    claim_text: str,
    relation: str,
    expected_source_sha256: str | None = None,
    reviewer_id: str | None = None,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    """Return a traceability record without asserting claim truth or support.

    An excerpt is considered traceable only when it is an exact substring of
    the provided source snapshot and the optional expected digest matches.
    Reviewer attribution is recorded only when both fields are supplied.
    """
    uri = _source_uri(source_uri)
    if not isinstance(source_text, str) or not source_text or len(source_text) > MAX_SOURCE_TEXT_CHARS:
        raise ValueError("source_text must be non-empty text within the 1 MB character limit.")
    quote = _required_text(excerpt, "excerpt", MAX_EXCERPT_CHARS)
    source_locator = _required_text(locator, "locator", MAX_LOCATOR_CHARS)
    normalized_claim_id = _required_text(claim_id, "claim_id", 120)
    normalized_claim_text = _required_text(claim_text, "claim_text", MAX_CLAIM_CHARS)
    if not isinstance(relation, str) or relation not in _RELATIONS:
        raise ValueError("relation must be supports, challenges or mentions.")

    source_digest = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    excerpt_digest = hashlib.sha256(quote.encode("utf-8")).hexdigest()
    if expected_source_sha256 is not None and (
        not isinstance(expected_source_sha256, str)
        or re.fullmatch(r"[a-fA-F0-9]{64}", expected_source_sha256) is None
    ):
        raise ValueError("expected_source_sha256 must be a 64-character SHA-256 digest.")

    digest_matches = expected_source_sha256 is None or (
        source_digest == expected_source_sha256.lower()
    )
    excerpt_found = quote in source_text
    if not digest_matches:
        traceability_status = "source_version_mismatch"
    elif excerpt_found:
        traceability_status = "exact_excerpt_found"
    else:
        traceability_status = "excerpt_not_found"

    if (reviewer_id is None) != (reviewed_at is None):
        raise ValueError("reviewer_id and reviewed_at must be supplied together.")
    reviewer = None
    review_time = None
    if reviewer_id is not None:
        reviewer = _required_text(reviewer_id, "reviewer_id", MAX_REVIEWER_ID_CHARS)
        review_time = _review_timestamp(reviewed_at)

    return {
        "schema_version": 1,
        "source_uri": uri,
        "source_sha256": source_digest,
        "excerpt_sha256": excerpt_digest,
        "excerpt": quote,
        "locator": source_locator,
        "claim_id": normalized_claim_id,
        "claim_text": normalized_claim_text,
        "reviewer_relation": relation,
        "traceability_status": traceability_status,
        "review_status": "reviewer_attributed" if reviewer else "unreviewed",
        "reviewer_id": reviewer,
        "reviewed_at": review_time,
        "claim_support_assessment": "not_machine_assessed",
        "source_credibility_assessment": "not_assessed",
        "independence_assessment": "not_assessed",
        "limitations": [
            "Exact excerpt matching proves only that the supplied text occurs in the supplied source snapshot.",
            "The locator is recorded but is not independently resolved to a page, paragraph or section.",
            "A reviewer relation label is an attributed judgement, not an automated finding that the claim is true.",
            "Source credibility, study methods, bias, context, causality and independent corroboration are not assessed.",
        ],
    }
