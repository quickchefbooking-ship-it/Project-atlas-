# Professor Learning Loop — Build Frame (2026-11-23)

## Objective
Connect existing lesson/memory, retrieval, evaluation, and improvement foundations into a measurable learning cycle. Learning must be incremental, evidence-grounded, reversible, and tenant-scoped.

## Cycle
1. **Observe:** capture task outcome, explicit user feedback, error category, and relevant metadata. Never capture secrets or raw sensitive payloads by default.
2. **Extract candidate:** produce a compact lesson candidate with source/provenance, scope, confidence, timestamps, expiry/decay, and privacy classification.
3. **Validate:** check schema, evidence, duplication, conflicts, injection risk, scope, and whether the candidate is a fact, preference, procedure, or episodic record. Candidates are untrusted until reviewed or validated by a bounded policy.
4. **Store:** append-only candidate record; approved memories may be versioned. Record supersession, deletion/retention controls, tenant/user ownership, and audit events.
5. **Retrieve:** query by semantic/keyword match, task scope, freshness, confidence, and provenance. Return source references and why each memory matched. Enforce tenant/user boundaries.
6. **Apply:** supply only relevant, bounded retrieved context to reasoning; treat memory content as data, never as executable instructions. User/system instructions take precedence.
7. **Evaluate:** compare task outcomes with and without the lesson using controlled, offline evaluation; track regressions, sample size, uncertainty, and evaluation version.
8. **Promote/rollback:** successful lesson usefulness can be promoted under explicit governance; harmful/obsolete memories can be quarantined, superseded, or rolled back. No autonomous code, policy, permission, or production changes.

## Memory classes
- Episodic: task/event records with retention controls.
- Semantic: facts with source and confidence.
- Procedural: tested steps/checklists, with version and evidence.
- Preference: explicit user preferences, scope and date.
- Candidate: untrusted proposed lessons pending validation.

## Acceptance criteria
- Each candidate has provenance, scope, confidence, privacy classification, and a stable ID.
- Retrieval is tenant/user isolated, bounded, explainable, and injection-resistant.
- Explicit correction updates/supersedes prior memory; conflict handling is deterministic and surfaced.
- Sensitive content is minimised; retention/deletion is enforceable.
- A lesson is not automatically promoted based solely on model confidence or one success.
- Evaluation produces reproducible results with baseline, lesson-enabled arm, criteria version, evidence, and regression checks.
- No external action, capability permission, code change, or production setting is changed by the learning loop.
- Unit/integration tests cover invalid, malicious, conflicting, stale, unscoped, and cross-tenant memory cases.

## Implementation sequence
A. Define memory schema/contracts and privacy policy.
B. Implement candidate extraction/validation and append-only lifecycle.
C. Implement retrieval adapter with provenance and access scoping.
D. Wire relevant memories into reasoning under prompt budgets.
E. Build offline evaluation harness and usefulness metrics.
F. Add explicit correction, quarantine, supersession, expiry, and rollback.
G. Add observability: counts, retrieval hit rate, feedback, regression, and lifecycle status.

## Status
Architecture/build plan only. This document does not claim the continuous loop is implemented or runtime verified.
