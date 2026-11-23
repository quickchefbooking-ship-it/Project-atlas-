# THE PROFESSOR — Matched Memory Retrieval Benchmark Protocol

Date: 2026-11-23
Status: characterization gate; synthetic data only

## Purpose
Measure the existing approved-memory lexical retrieval behavior before changing scoring. All candidate scoring changes must be evaluated against the same queries, corpus, authorization/eligibility filters, and cutoffs.

## Baseline behavior
The current repository uses:
- Original query-term overlap weighted by field: title 4, category 3, content 2.
- Known synonym expansion contributes 2 points per expanded-only overlap.
- A candidate is returned at score >= 2.
- Ranking is score, then created_at, then proposal_id (descending).
- Candidate eligibility is restricted to approved, unexpired, owner/tenant-scoped records and excludes superseded memories.
- Retrieval is bounded (limit <= 20).

## Existing synthetic suites
- Expanded labelled benchmark: 8 answerable cases and 1 no-answer case, with Recall@3 threshold 0.875, MRR and Precision@3 calculated for diagnostics, and explicit no-answer abstention.
- Focused distractor suite: 6 answerable cases and 2 no-answer cases, strict Recall@3 = 1.0 and no-answer abstention.
- Conflict characterization: checks conflicting memories remain retrievable; the pipeline preserves both for clarification rather than automatically resolving them.
- Trace checks: opt-in bounded provenance metadata; no query or memory content emitted.

## Matched comparison requirements
Any proposed scorer must be compared on identical fixtures and queries:
1. Recall@1, Recall@3, Recall@5 (answerable queries).
2. Precision@3 and Precision@5 (per-query average; empty result contributes zero).
3. Mean Reciprocal Rank (MRR).
4. No-answer false-positive rate and abstention.
5. Conflict retention: both conflicting records remain available when eligible.
6. Eligibility/privacy invariants: owner/tenant isolation, approval, expiry, supersession, and bounded output.
7. Deterministic tie-breaking.

Report results per query and aggregate; do not conceal regressions behind averages.

## Limits
This is a small synthetic lexical benchmark, not evidence of semantic understanding, production reliability, or real-user performance. No scorer change is justified by this document. Baseline numbers must be produced by an executable run before a candidate is accepted.
