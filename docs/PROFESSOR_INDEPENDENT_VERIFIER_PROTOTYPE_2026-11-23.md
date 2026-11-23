# Independent deterministic verifier prototype — 2026-11-23

## Goal
Create a separate, testable gate for explicit fact coverage, contradictions,
constraints, source availability/citation presence, and evidence-free abstention.

## Scope
This prototype is **not runtime-wired**. It uses fixture-defined phrase rules
and source IDs. It is not semantic verification, cannot understand paraphrases,
and cannot establish that a source itself is true. Phrase matching can produce
false positives/negatives. It is a test harness and a contract sketch.

## Behavior
- Every expected fact must match one supported phrase.
- Any listed contradiction phrase overrides a supported phrase for that fact.
- Required constraints are checked by normalized phrase presence.
- A required source must be both available in the fixture and cited by its ID.
- A fact's declared `source_id` automatically becomes a source requirement, so the fact cannot pass without its source being available and cited.
- When an evidence-free abstention is required, the answer must signal uncertainty
  and there must be no required facts or constraints.
- Adversarial text is treated as answer content, not executable instructions.

## Test matrix
1. Complete supported answer passes.
2. Contradiction fails even if the correct phrase also appears.
3. Missing fact and missing constraint fail.
4. Citation-shaped token with no available source fails.
5. Adversarial text containing a contradiction fails.
6. No-evidence abstention passes under explicit abstention fixture.
7. Uncertainty does not satisfy a fact-bearing request.
8. A fact-linked source must be cited even when available.

## Next gate
If this characterization is useful, the next iteration should replace phrase rules
with a source-grounded claim extraction/verifier interface, while retaining
independent fixture labels and adversarial tests. Any model-assisted verifier
must be evaluated against a held-out set, report uncertainty, and remain
non-authoritative until calibrated. No runtime integration is proposed here.
