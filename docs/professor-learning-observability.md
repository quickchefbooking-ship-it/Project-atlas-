# Professor learning observability — implementation contract

**Status:** engineering specification for the existing AtlasOnePro Professor prototype. This document does not claim that a learning dashboard or complete learning lifecycle is already implemented.

## Objective

Make the Professor's learning behaviour inspectable without presenting stored notes as intelligence or inventing progress. The monitor must distinguish:

1. **Recorded experience** — tasks, attempts and evaluations that actually exist in SQLite.
2. **Proposed learning** — unvalidated lesson records associated with an outcome.
3. **Reviewed knowledge** — lessons that have passed an explicit, attributable review gate.
4. **Demonstrated improvement** — a later, comparable evaluation showing a measurable improvement after an approved lesson was eligible for retrieval.

Only the fourth category is evidence that reusing a lesson improved performance. A lesson count alone is not a learning-success metric.

## Current verified data and limitations

The current prototype persists tasks, task attempts, evaluations and lessons. Lesson creation forces `validated=false`; the creator cannot self-validate. Retrieval searches only validated lessons. Evaluation is deterministic and does not support subjective criteria. The existing API-key control is shared-secret authentication; reviewer/actor labels are caller-supplied metadata, not verified identity.

The current schema does not record a complete lesson-review history, a verified reviewer identity, lesson-to-later-task usage, or a controlled before/after evaluation cohort. Therefore the first monitor must not display a fabricated approval count, improvement rate, or “last learning event”.

## First delivery — read-only monitor

Add a protected, read-only endpoint (proposed: `GET /learning/overview`) and a small operator view in the existing Professor interface. Do not create a separate app.

The endpoint should return only aggregates and bounded, sanitised recent records derived from persisted data:

- task totals by terminal/current status;
- evaluation totals and deterministic pass rate, with denominator and date range explicit;
- lesson totals split into validated and unvalidated;
- recent lesson metadata: lesson ID, task ID, type, summary, source, created timestamp and validation flag;
- recent task/evaluation references sufficient to inspect the recorded outcome;
- explicit capability flags stating that reviewer identity, lesson-use attribution and comparative improvement measurement are not yet available.

Never expose API keys, credentials, raw exception messages, full task descriptions, private source-document bodies, retry idempotency keys or internal policy snapshots. Apply strict result limits and stable ordering. A zero count means zero persisted records in the selected database, not that the Professor has never learned in another environment.

The view must show **Not measured** rather than 0% when a metric cannot validly be calculated. Every rate must show numerator, denominator, evaluation method and time window. Do not mix deterministic evaluations with future subjective reviews.

## Second delivery — auditable lesson review

Do not enable lesson promotion through the current shared API-key route. First design a review-history table and migration with:

- immutable review event ID and lesson ID;
- decision: approve, reject, request-correction, supersede or withdraw;
- timestamp and reason;
- reviewer subject ID from a verified identity provider (not a free-text name);
- evidence references and evidence digest;
- previous and resulting lesson state;
- append-only history, with correction/withdrawal events rather than destructive edits.

Until verified identity and authorisation exist, the monitor may display the existing validation flag as legacy state, but must label its reviewer provenance as unverified. No new UI control should imply that a click is a secure approval.

## Third delivery — demonstrate improvement

Record lesson retrieval/use against the task and attempt that actually received it. Preserve lesson ID/version, retrieval timestamp, retrieval method, evaluator version and task cohort metadata. Do not store secrets or duplicate entire private source documents in the event.

A comparative improvement claim requires a documented evaluation protocol:

- fixed, versioned task set and deterministic acceptance criteria;
- baseline runs before lesson availability and follow-up runs after availability;
- equivalent execution conditions and bounded retries;
- explicit treatment of failed, cancelled and missing runs;
- no cherry-picking of only successful examples;
- reproducible aggregation with sample size and uncertainty/limitations.

Report a measured change only when both cohorts are present and comparable. Otherwise show **Insufficient evidence**. Correlation between lesson availability and a better score is not, by itself, proof that the lesson caused the improvement.

## Security and product boundaries

- Read-only monitor first; no lesson promotion, task execution, external integrations or scheduler controls in this delivery.
- Use the existing database and application; no Replit dependency or paid provider.
- Do not expose the prototype as a public multi-user service.
- Keep all external actions, trading, payments, publishing, sending, purchases and deletion disabled or separately approval-gated.
- Do not merge, deploy, publish or change production as part of this work.
- A green test suite is necessary but not sufficient for security or release readiness.

## Acceptance criteria

1. Overview values are calculated from persisted records, never hard-coded demonstration values.
2. Empty databases return valid zero counts and “Not measured” where denominators or cohorts are absent.
3. Pass-rate output includes numerator, denominator, evaluation method and time window.
4. Unvalidated lessons are visibly distinct and are never counted as approved knowledge.
5. The endpoint is protected by the existing API-key dependency and is clearly labelled as prototype-level shared-key access.
6. Responses are bounded, stable and exclude sensitive task/source payloads and internal execution secrets.
7. Tests cover empty state, mixed lesson validation states, deterministic pass/fail totals, malformed stored evidence, ordering, bounds and authentication.
8. The UI labels the monitor as an observability view, not proof of autonomous or self-improving intelligence.

## Implementation sequence

1. Review the existing storage query helpers and dashboard UI before changing schema.
2. Implement read-only aggregate queries with explicit SQL grouping and bounded recent-record queries.
3. Add response models and the protected overview route.
4. Add unit/API tests for calculation, privacy, bounds and authentication.
5. Add the operator view to the existing Professor interface; render unavailable measures as “Not measured”.
6. Run the full existing test suite and inspect the resulting GitHub Actions run.
7. Only then design the separately gated review-history and lesson-use event migrations.

**Current truthful status:** the Professor records outcomes and proposes unvalidated lessons, and it reuses only lessons marked validated. This is a foundation for governed learning; the monitor and measured improvement loop described here are future implementation work.
