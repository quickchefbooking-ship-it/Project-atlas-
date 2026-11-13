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
