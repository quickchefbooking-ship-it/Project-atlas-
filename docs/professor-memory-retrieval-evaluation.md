# Professor memory retrieval evaluation

## Purpose

This is a small, deterministic, offline smoke benchmark for the current lexical
memory retrieval baseline. Its synthetic corpus lives in
`tests/test_professor_memory_retrieval_evaluation.py` and is deliberately
separate from application data.

## Safety and scope

- Uses synthetic project, preference and interface records only.
- Uses an in-memory SQLite database and the existing tenant/owner-scoped
  repository API.
- Explicitly approves fixture memories through the same repository workflow.
- Does not load real user memories, call a model, access the network, or write
  persistent application data.
- Does not change retrieval ranking or production behavior.

## Metrics

For each query, the test compares the ranked proposal IDs with a manually
labelled set of relevant IDs:

- **Recall@3**: relevant retrieved items in the first three divided by all
  relevant items for that query.
- **Precision@3**: relevant retrieved items in the first three divided by
  three.
- **MRR**: reciprocal of the rank of the first relevant result, or zero when
  none is retrieved.

The test asserts a modest regression floor across the curated cases. The
corpus is intentionally small and lexical, so passing it demonstrates only
that the known smoke cases remain retrievable. It is not evidence of semantic
understanding, unbiased relevance, or production-grade retrieval quality.

## Next evaluation work

Expand the labelled query set with paraphrases, ambiguous queries, deliberate
distractors, conflicting/updated memories, multilingual examples and queries
with no relevant result. Review labels independently before using the corpus
to tune ranking weights. Report per-query failures as well as aggregate
metrics; do not hide a poor case behind an average.
