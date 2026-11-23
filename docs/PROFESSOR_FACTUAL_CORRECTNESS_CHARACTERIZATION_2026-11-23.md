# THE PROFESSOR — Factual Correctness Characterization

Date: 2026-11-23
Status: Synthetic test characterization only

## Finding
The current pre-delivery critique is deterministic and transparent, but it
measures lexical goal/constraint overlap and citation-ID presence. These are
not semantic correctness checks.

## Reproducible gap
Synthetic tests demonstrate that an answer can:
- repeat enough goal wording to meet the lexical coverage threshold;
- contain a constraint's words;
- assert a deliberately false fact (or omit a labelled expected fact);
- and still be accepted by the current critique.

This PR adds characterization tests only. It does not change runtime behavior,
provider configuration, memory retrieval, action boundaries, or execution.

## Why this is not a correctness solution
The expected-fact labels in these fixtures are independent of the critique.
They are assertions used to demonstrate the gap, not a general fact verifier.
A robust future evaluator should have separately labelled atomic facts and
constraints, test contradiction and omission, and report false-accept/false-
reject rates on a matched synthetic suite. A model-based judge, if explored,
must be treated as an additional fallible signal and cannot replace deterministic
safety gates.

## Gate recommendation
Do not describe lexical critique as factual verification. Keep delivery
fail-closed for existing safety boundaries. Before changing runtime acceptance,
build a matched evaluation set, report per-case outcomes, and compare the
baseline and proposed evaluator.
