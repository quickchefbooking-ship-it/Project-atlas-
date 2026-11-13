# Professor lesson-use attribution — design and safety contract

**Status:** design-only proposal. No schema migration, runtime instrumentation, lesson promotion, or external action is implemented by this document.

## Purpose

The learning monitor can count lesson records, but it cannot yet answer whether a particular lesson was actually supplied to a later task or whether that task's result changed. This design defines the minimum evidence needed before Professor may report lesson reuse or measured improvement.

## Event model

Introduce an append-only `lesson_use_events` record only after a reviewed implementation plan and migration review. Each event should contain:

- immutable event ID;
- task ID and attempt ID that received the lesson;
- lesson ID and immutable lesson version/digest;
- retrieval timestamp;
- retrieval source/mode (for example, validated local retrieval);
- evaluator method and evaluator version for the receiving attempt;
- correlation/request ID suitable for tracing, but no credentials or raw prompt content.

The event must be written only when a lesson is actually included in the task's execution context—not merely when a search returns a candidate. A retrieval candidate that is discarded must not be counted as a use.

## Data integrity

- Foreign keys must reference existing task, attempt and lesson records.
- A lesson's identity/version must remain stable after use; edits create a new version or digest.
- Events are append-only. Corrections use compensating events, never destructive edits.
- Duplicate event delivery must be idempotent using a unique event ID and/or deterministic idempotency key.
- Record the event and the task-attempt transition transactionally where feasible, so a crash cannot leave a false usage record.
- Missing or malformed references fail closed: do not count the event.
- Do not store lesson evidence JSON, source document bodies, secrets, API keys, full task descriptions, or private execution payloads in the attribution table.

## Honest reporting

The monitor may report:
- lessons retrieved as candidates;
- lessons actually supplied to an attempt;
- task/attempt outcomes associated with those uses;
- counts grouped by lesson version and evaluator version.

It must not label these counts as proof of improvement. A better outcome after lesson use may be correlation, selection bias, or task-mix variation.

Improvement reporting remains **Not measured** until a documented protocol supplies:
1. a fixed, versioned evaluation set;
2. comparable baseline and follow-up runs;
3. the same evaluator version and execution limits;
4. all eligible runs, including failures, cancellations and missing results;
5. sample sizes and uncertainty/limitations;
6. a reproducible calculation.

## Migration and compatibility plan

1. Inspect the actual task, attempt, lesson and evaluation schemas on the target branch.
2. Confirm SQLite foreign-key enforcement and transaction boundaries.
3. Add a forward-only migration with a schema version and rollback/recovery notes.
4. Add tests for foreign-key failures, duplicate events, crash boundaries, ordering, lesson version changes, and privacy exclusions.
5. Instrument the single point where validated lesson content is attached to an attempt.
6. Verify event counts against controlled fixtures before exposing them in the monitor.
7. Keep old records as unknown attribution; never backfill inferred lesson use.

## Security and product boundaries

- Do not add approval buttons or reviewer identity claims here.
- Do not promote lessons or change the current validated-only retrieval rule.
- Do not add autonomous retries, schedulers, trading, payments, publishing, email sending, purchases, or deletion.
- Do not merge, deploy, publish, or alter production as part of this design step.
- Use the existing repository and free GitHub workflow; no Replit or paid service.

## Acceptance criteria for a future implementation

- A use event means the lesson was actually included in the attempt context.
- Event identity is stable and duplicate-safe.
- Event creation is transactionally consistent with attempt execution.
- No private evidence, source content, task payload or secret is copied into the event.
- Historical records without proof remain unattributed.
- The dashboard distinguishes candidate retrieval from actual use.
- Improvement remains Not measured until comparable cohorts and a documented protocol exist.

**Current truthful status:** Professor records outcomes and stores lesson validation flags. This proposal does not claim that lesson-use attribution or measured self-improvement exists yet.


## Verified implementation inspection (2026-11-13)

The current Professor source was inspected before proposing a migration:

- `atlas_engine/storage.py` creates `tasks`, `task_attempts`, `evaluations` and `lessons`. `task_attempts.attempt_id` and `lessons.id` are primary keys; both are linked to `tasks.id`. SQLite foreign-key enforcement is enabled in the shared connection factory.
- `atlas_engine/task_manager.py` claims a fenced task attempt, retrieves validated lessons through `LearningMemory.get_relevant_lessons`, and passes the resulting list to `executor.execute` as `relevant_lessons`.
- `atlas_engine/executor.py` currently implements only the bounded local arithmetic executor. It reads the task description and deadline; it does not read or consume `relevant_lessons`. Paid/external AI execution is not implemented.
- Task completion and its evaluation are persisted atomically by the existing completion transaction. Failure lessons are saved after that transaction and are forced unvalidated.

### Consequence for the first implementation

There is currently no executor that consumes lesson content. Therefore the present runtime can truthfully record **candidate retrieval** (if separately instrumented), but it cannot truthfully record **lesson use**. No `lesson_use_events` table or write helper should be added until an executor has an explicit, testable contract proving which lesson IDs it consumed. Otherwise an internal caller could record a false use merely by passing IDs to storage.

### Safe next sequence

1. Keep the current retrieval-only behaviour unchanged.
2. Add an explicit executor result contract in a future capability-aware executor, e.g. a bounded list of lesson IDs actually consumed, validated against the exact lesson context supplied to that attempt.
3. Add the append-only event write inside the same transaction that commits the task outcome/evaluation, after validating the attempt fencing token and the consumed lesson IDs. Do not create an event for a failed-to-commit attempt.
4. Add tests proving that the arithmetic executor reports no consumed lessons, forged/unknown IDs are rejected, duplicate event IDs are idempotent, and event writes roll back with task completion.
5. Only then expose candidate retrieval and confirmed use as separate dashboard metrics.

This inspection intentionally blocks a premature schema migration. It avoids storing false-positive usage events and avoids modifying a stable task completion transaction before the consumption contract exists.
