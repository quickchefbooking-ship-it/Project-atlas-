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
8. A fact-linked source must be cited even when available.\n9. A negated supported phrase must be treated as a contradiction.
10. ‘Not only’ is not misread as negation.

### Context-hardening extension (points 3–7)
- A draft claim explicitly marked unverified does not count as established support.
- Hedged facts (e.g. ‘possibly’) do not count as established support.
- Disputed facts do not count as established support.
- A mere mention in an email does not count as source confirmation.

These are narrow lexical characterizations, not general language understanding. The
phrase-window rules can still misclassify context and need broader held-out tests.

## Next gate
If this characterization is useful, the next iteration should replace phrase rules
with a source-grounded claim extraction/verifier interface, while retaining
independent fixture labels and adversarial tests. Any model-assisted verifier
must be evaluated against a held-out set, report uncertainty, and remain
non-authoritative until calibrated. No runtime integration is proposed here.


## Evaluation expansion — 10 additional boundary cases

The second iteration adds checks for sentence/clause scoping, fact isolation, marker leakage, irrelevant keywords, fixture-only paraphrase limits, quote handling, and per-fact contradiction. Sentence and semicolon boundaries scope negation and uncertainty markers. A regression exposed that the verifier was passing normalized text into the context helpers, which erased sentence boundaries and caused unrelated markers to leak; this has been fixed by passing the original answer text. A regression test now requires an unrelated unverified sentence not to false-reject supported facts. The next evaluation iteration now treats matching phrases inside straight or curly quotation marks as reported speech rather than asserted support. This is deliberately conservative: even a separate unquoted assertion of the same phrase may be rejected when a quoted occurrence is also present. Quote parsing remains a lexical heuristic, not a general model of attribution or speaker intent. This does not establish semantic truth.


## Quotation-context evaluation — 2026-11-24

- Matching required phrases inside straight or curly quotation marks are no longer accepted as assertions.
- Regression tests cover straight quotes, curly quotes, and a phrase appearing both asserted and quoted.
- The rule is intentionally conservative and may reject valid answers that quote a phrase while also asserting it elsewhere.
- This remains a fixture-based lexical gate; it does not identify speakers, validate source attribution, or establish source truth.


## Source-attribution evaluation — 2026-11-24

Fact-linked source IDs must now appear in the same sentence as the matching claim
or in the immediately following citation sentence. A source token elsewhere in
the answer is not sufficient to attribute it to the fact. Tests cover adjacent,
same-sentence, distant, and unavailable-source cases. This is still only a
lexical proximity heuristic: it does not read source contents, prove that a
source supports a claim, or resolve complex multi-claim attribution.



## Source-content evaluation — 2026-11-24

The next fixture layer introduces explicit `SourceEvidence(source_id, text)`
records. When source evidence is supplied, a fact-linked source must contain a
matching supported phrase in a narrow asserted context. The evaluator
characterizes denials, allegation/hedge markers, quoted or glossary/example
mentions, absent evidence, wrong source IDs, partial coverage of multiple facts,
and conflicting evidence. Conflicting evidence is surfaced rather than silently
resolved.

This remains a lexical fixture test, not semantic source understanding. It does
not prove that the source is authentic, authoritative, current, complete, or
truthful. It does not safely interpret complex grammar, paraphrases, speaker
attribution, or multi-hop evidence. Source-content checking is opt-in for
backward-compatible fixture cases and is not connected to the live Professor.



## Fact-level evidence coverage — 2026-11-24

The evaluator now reports source-content gaps and conflicts at the individual
fact ID level as well as the source ID level. This prevents a source ID that
supports one fact from concealing that it does not support a second fact which
happens to cite the same source. Tests cover partial support, fact-specific
conflicts, and separate sources supporting separate facts. This remains a
fixture-only lexical check and does not interpret compound natural-language
claims or establish semantic entailment.
