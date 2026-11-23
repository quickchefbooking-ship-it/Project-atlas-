# Expanded Professor memory retrieval benchmark

## Purpose

`tests/test_professor_retrieval_expanded_benchmark.py` adds a synthetic, labelled
diagnostic set for the current deterministic lexical retrieval baseline.

## Coverage

- Paraphrased queries (not exact title copies)
- A deliberate distractor memory
- A no-answer query, which must retrieve no unrelated records
- Explicitly superseded preference memory, which must be excluded

## Interpretation

The current retrieval implementation is lexical overlap with weighted title,
category and content terms. It is not semantic retrieval. The benchmark should
be used to expose failures and guide the next iteration, not to claim language
understanding.

The per-query diagnostics preserve failing examples. The CI floor is a
regression guard only and is intentionally modest; no aggregate score is a
substitute for reviewing individual failures.

## Next steps

1. Run this benchmark and capture the actual baseline.
2. Review failures by query category and distinguish vocabulary mismatch from
   ranking failure.
3. Implement a candidate improvement behind a deterministic offline test.
4. Compare baseline and candidate on exactly the same corpus and queries.
5. Retain only improvements that do not regress owner/tenant isolation,
   approval, expiry, rejection, supersession or no-answer behavior.
6. Do not use real personal memory or enable automatic promotion.
