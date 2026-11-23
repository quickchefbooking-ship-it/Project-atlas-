# Expanded factual evaluation characterization — 2026-11-23

## Purpose
Extend the tiny four-case synthetic fixture with seven categories: paraphrase,
partial contradiction, multiple facts, irrelevant keyword-heavy content,
uncertainty calibration, adversarial context, and no-answer abstention.

## Method
- Labels are fixed fixture metadata and are not generated from the critique.
- Each answer is passed through the existing deterministic lexical critique.
- This suite characterizes the critique; it does not provide semantic verification.
- All text is synthetic. No real user data, external providers, or runtime behavior
  is involved.

## Expected characterization
| Category | Fixture label | Critique expected |
|---|---|---|
| Paraphrase | Answerable | Accept |
| Partial contradiction | Incorrect | Accept (false acceptance) |
| Multiple facts | Correct | Accept |
| Irrelevant keyword-heavy | Incorrect | Accept (false acceptance) |
| Uncertainty calibration | Uncertain | Accept (not calibrated) |
| Adversarial context | Incorrect | Accept (false acceptance) |
| No answer | Abstain | Reject |

The expanded set is intentionally small and hand-authored. The results must not be
presented as general accuracy, reliability, or production readiness. In particular,
phrase overlap is not proof of fact coverage, contradiction detection, calibrated
uncertainty, or resistance to adversarial content.

## Gate implication
Before the critique is trusted for factual acceptance, THE PROFESSOR needs an
independent fact/constraint verifier with source-grounded checking, contradiction
handling, uncertainty rules, and adversarial evaluation. This PR only adds
characterization tests and documentation; it does not change runtime logic,
execution boundaries, providers, memory, or external actions.
