# THE PROFESSOR — Matched Synthetic Factual Evaluation

Date: 2026-11-23
Status: Baseline characterization, synthetic fixtures only

## Purpose
Compare the existing lexical critique with fixture-owned correctness labels.
The expected facts and contradictions are defined independently from
`critique_answer`; the benchmark must not reuse critique output to define
truth.

## Initial matched set
Four cases:
1. Correct expected fact, constraint covered.
2. Contradiction ("zero layers" vs expected "three layers") while retaining
   goal and constraint keyword overlap.
3. Omission of the expected fact while retaining goal and constraint overlap.
4. Correct expected fact but omission of the stated constraint.

A separate evidence fixture checks that citation-ID presence is not source
verification.

## Baseline characterized by tests
On the four cases, the current critique has:
- True accepts: 1
- False accepts: 2
- False rejects: 1
- False-accept rate: 2/4 = 50% (synthetic case set)
- False-reject rate: 1/4 = 25% (synthetic case set)

These are not general performance estimates. The fixture is intentionally tiny
and constructed to expose known behaviors.

## Limitations
- Labels use explicit fixture phrases; this is a deterministic test oracle,
  not a general semantic evaluator.
- Four cases are too small to estimate real-world accuracy.
- Citation-ID presence does not prove source support or entailment.
- No runtime changes, provider calls, memory changes, or execution capability
  were introduced.

## Next gate
Expand with paraphrase pairs, multi-fact answers, partial contradictions,
uncertainty calibration, irrelevant but keyword-heavy answers, conflict
preservation, and adversarial instruction content. Report metrics per category
and keep the existing safety boundaries as hard independent gates.
