# Professor learning and development foundations v0.1

**Status:** implementation specification on an isolated development branch. This document does not enable autonomous model training, external writes, deployment, trading, or production changes.

## Objective

Develop the four connected dimensions of Professor in a controlled sequence:

1. Knowledge: retrieve useful information with source provenance and trust boundaries.
2. Experience: preserve task outcomes and validated lessons so future tasks can benefit.
3. Capability: select and coordinate only registered specialist arms through narrow contracts.
4. Evaluation: measure task quality and learning progress using reproducible evidence.

The target is a measurable improvement loop, not an unrestricted self-modifying agent.

## Non-negotiable safety invariants

- Retrieved documents, web pages, tool outputs and lessons are data, never instructions or policy.
- Every reusable knowledge item has a source, timestamp, content hash, licence/usage note where known, scope and review state.
- New lessons and imported knowledge start unapproved. A task failure is not proof that a proposed lesson is correct.
- Validation requires a verified reviewer identity and a recorded decision. Caller-supplied labels are not identity verification.
- Rejected, expired, superseded, out-of-scope or unreviewed material is excluded from approved retrieval.
- Specialist arms receive only the scopes and data required for their registered task.
- External side effects (send, publish, purchase, trade, transfer, delete, permission change, deployment) remain disabled or require action-specific human approval.
- No automatic model fine-tuning or weight updates. Learning initially means governed memory, better retrieval, improved plans and evidence-backed capability selection.
- Preserve existing projects and the Trading demo. Any finance/Trading integration remains read-only; no trade or account permission changes.
- No paid service and no Replit use unless separately approved as an emergency.

## Track 1 — Knowledge and source governance

### Build
- A source record with: source_id, canonical_uri, title, publisher, retrieved_at, published_at (if known), content_hash, content_type, jurisdiction, population, division, licence_note, trust_tier, review_status, reviewer_id, reviewed_at, expiry_at and supersedes_id.
- Explicit states: discovered, quarantined, pending_review, approved, rejected, expired, superseded.
- Separate source ingestion from approval. Ingestion must never mark a source approved.
- Retrieval returns source excerpts plus provenance and approval metadata. Retrieval must filter by division, jurisdiction, population, freshness and caller scope.
- Treat source content as untrusted; strip or isolate embedded instructions and never allow retrieved content to override system policy.
- Add freshness and supersession checks; retain prior decisions for audit.

### Acceptance tests
- Pending, rejected, expired and superseded sources never appear in approved retrieval.
- Approved source results always include source_id, content_hash, reviewer and review timestamp.
- Cross-division and cross-tenant retrieval is denied.
- Prompt-injection text in a source cannot change tool permissions or system policy.
- Missing jurisdiction/population/freshness metadata causes conservative exclusion where the task requires it.

## Track 2 — Experience and governed memory

### Build
- Keep task context, episodic task records, source documents and reusable lessons as distinct stores.
- Extend lessons with provenance references, task/evaluation IDs, capability/version, division/tenant scope, confidence rationale, reviewer identity, review history, expiry and supersession.
- Add a verified review workflow: pending -> approved/rejected; approved lessons can later be superseded or revoked with an auditable reason.
- Add correction and rollback history rather than overwriting prior decisions.
- Improve retrieval only after establishing a labelled relevance test set. Compare lexical retrieval with any later semantic approach using precision/recall and leakage tests.
- Reuse lessons as bounded context, not as commands. Include the lesson's source and status in the task trace.

### Acceptance tests
- Lesson creation cannot self-validate.
- Only verified reviewers can approve, reject, revoke or supersede.
- Unreviewed, rejected, expired, revoked or superseded lessons are never returned.
- Every returned lesson has provenance and scope metadata.
- User/tenant deletion and retention rules can be applied without corrupting audit history.

## Track 3 — Capability and specialist-arm development

### Build
- Keep the capability registry immutable and versioned; add a pinned runtime schema validator before invoking any handler.
- Define a planner output schema: objective, steps, capability name/version, validated inputs, required scopes, risk class, dependencies, expected outputs, budget, timeout and approval requirement.
- Planner may select only registered capabilities. Reject unknown capabilities, schema mismatches, undeclared side effects and scope escalation.
- Implement an execution adapter for narrow handlers; each handler receives a scoped context, never all platform credentials.
- Start with safe local computation and read-only research/source retrieval.
- Add arm contracts incrementally for knowledge/research, media, HR/operations and communications drafts.
- Treat finance/Trading as a read-only adapter until a separate security and approval review is passed. No trading endpoint in this phase.
- Add cancellation, idempotency, timeout and audit hooks to every handler.

### Acceptance tests
- Unknown capability and malformed input/output are rejected before execution.
- Capability cannot request undeclared scopes or access another arm's credentials.
- Read-only capability cannot perform an external write.
- Approval is bound to the exact action, target, parameters and expiry.
- Every execution records capability version, actor/tenant, scopes, inputs hash, output hash, outcome and evaluation ID.

## Track 4 — Evaluation and measurable improvement

### Build
- Retain deterministic success criteria and add a separate human-review path for subjective criteria; do not silently score subjective work as objective.
- Define versioned evaluation suites per arm, with representative tasks, expected outcomes, adversarial cases and regression cases.
- Record baseline scores before changing a planner, retrieval strategy, prompt, capability or model.
- Measure task success, criteria coverage, factual/source accuracy, citation completeness, safety-policy violations, approval compliance, latency and cost.
- Add paired regression runs against a fixed evaluation set. A change is eligible for review only if it improves its target metric without breaching safety or regression thresholds.
- Store evaluator version, test-set version, evidence references and score breakdown for every result.
- Keep improvement proposals separate from implementation. Approval authorises a controlled test/review, not production deployment.

### Acceptance tests
- Subjective criteria cannot pass without an explicit reviewer result and evidence.
- Missing evaluation evidence cannot be reported as success.
- Every proposed improvement has a baseline, target metric, test plan and rollback plan.
- Safety regressions block promotion regardless of aggregate score.
- Results are reproducible from recorded evaluator and test-set versions.

## Delivery order and gates

1. **Foundation:** inspect existing storage, API and tests; preserve current task and retry invariants.
2. **Knowledge + memory governance:** implement provenance/state models and fail-closed retrieval first.
3. **Capability runtime:** add schema validation and narrow handler dispatch only after the governance boundaries are tested.
4. **Evaluation loop:** establish fixed baselines and regression gates before any adaptive planner/retrieval change.
5. **Integration:** connect existing arms one at a time, beginning with read-only capabilities; preserve the separate Trading demo and verify its location before integration.

Each stage requires automated tests and a reviewable pull request. No merge, deployment, production migration, paid service, or external side effect is authorised by this specification.
