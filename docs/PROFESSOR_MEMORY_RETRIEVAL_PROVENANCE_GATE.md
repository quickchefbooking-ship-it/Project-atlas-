# Professor Memory Retrieval Provenance — Design Gate

Status: proposal only; no runtime changes.

## Current retrieval behavior
The tenant memory repository performs bounded lexical retrieval over approved, unexpired, owner-scoped records. It excludes superseded memories, scores exact term overlap across title/category/content, adds a conservative synonym-group score, and returns matched_terms and matched_fields. The current result does not expose the total score or a structured retrieval trace.

## Desired trace (bounded and auditable)
For each candidate actually returned, a future trace may include:
- proposal ID (stable reference)
- retrieval algorithm/version
- query normalization version
- matched query terms (not the full query)
- matched fields: title/category/content
- whether synonym expansion contributed
- bounded score breakdown (exact-title, exact-category, exact-content, synonym contribution)
- rank and retrieval limit
- approval/expiry/supersession eligibility checks as booleans or reason codes

## Privacy and safety constraints
- Never log full memory content or the user's full query by default.
- Trace only records visible to the same authenticated tenant/owner scope.
- Do not expose hidden or rejected memories in trace output.
- Do not let trace metadata become instructions; it is evidence explaining retrieval.
- Avoid retaining traces indefinitely; define retention and deletion behavior before implementation.
- Do not claim semantic understanding from lexical score.

## Acceptance gates before runtime implementation
1. Trace data is deterministic for the same repository state and query.
2. Every returned candidate can be explained by a score breakdown.
3. Superseded, expired, pending, rejected, and cross-owner records are absent.
4. No-answer and low-confidence behavior remains unchanged or improves.
5. Tests assert trace privacy and tenant/owner isolation.
6. Benchmark comparison shows no regression in Recall@K, Precision@K, MRR, abstention, or conflict preservation.

## Next implementation step
Add an opt-in, structured explanation method (not default logging) that returns candidate IDs, matched terms/fields, and score components while preserving the existing retrieval API. Review its privacy surface before wiring traces into the reasoning pipeline.