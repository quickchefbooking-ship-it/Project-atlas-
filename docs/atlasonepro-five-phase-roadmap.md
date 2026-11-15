# AtlasOnePro Professor — Five-phase delivery roadmap

**Purpose:** a gated engineering plan for building the Professor into a reliable, secure orchestration system with specialist capability arms. This roadmap is a delivery plan, not a claim that future capabilities are already live.

## Programme rules

- Work in phase order. A phase is complete only when its acceptance tests and evidence are recorded.
- Preserve existing working systems and use the current recovery branch. Do not create duplicate projects.
- Keep paid services disabled unless Ashley explicitly approves them.
- Keep external integrations read-only or draft-only until their permissions, identity and approval controls are proven.
- Never merge, deploy, publish, change production or alter main without a separate explicit approval.
- A green test suite is necessary but not sufficient for production readiness.

## Phase 1 — Safe crash recovery

**Status: prototype implementation complete; awaiting review with PR #1.**

Delivered on the recovery branch:
- Durable task-attempt records with worker ID, attempt number, fencing token, heartbeat and lease expiry.
- Atomic leased task claims and heartbeat ownership checks.
- Background heartbeat during Professor execution.
- Atomic persistence of task outcome, evaluation and lease completion.
- Bounded task intake: 200-character titles, 10,000-character descriptions, at most 100 success-criteria entries and 16 KiB of finite UTF-8 criteria JSON. Invalid-request responses omit echoed request values and validation context.
- Expired attempts are held as recovery_required; no automatic requeue or replay.
- Authenticated inspection and expiry-scan routes.
- Explicit mark_failed and retry decisions with an audit record. Retry requires explicit retry_safe and side_effects_reconciled attestations and never starts automatically.
- Regression coverage for concurrent claims, heartbeat ownership, expiry, restart persistence, recovery decisions and authenticated routes.

Acceptance evidence: latest push and PR workflows each passed 115 tests with one non-blocking Starlette/AnyIO deprecation warning. See PR #1 and docs/task-crash-recovery-phase-1.md.

Remaining Phase 1 limitations: local SQLite only; no distributed worker coordination; recovery actor labels are not verified identity; side-effect reconciliation is caller-attested rather than independently proven.

## Phase 2 — Bounded retries and cancellation

**Status: policy foundation, durable cancellation and retry-schedule primitives implemented; unattended retries remain disabled.**

Design and acceptance matrix: `docs/phase-2-retry-cancellation-design.md`.

Implemented:
- Typed retryable/terminal error classes and a pure fail-closed eligibility evaluator.
- Immutable server-side retry ceilings, finite timing validation, bounded jittered back-off and a frozen capability error-code allowlist.
- Capability contracts require explicit boolean safety declarations and a non-empty test-evidence reference before they are considered retry-safe.
- Durable, idempotent cancellation requests per task attempt, with requested, acknowledged, too_late and requires_recovery states.
- Authenticated cancellation request/status routes.
- Fenced cancellation acknowledgement and atomic task/evaluation/attempt persistence.
- Cooperative cancellation checks before execution, after context retrieval, after the local executor returns and before normal completion.
- Expired worker cancellation requests move to operator recovery; completed attempts record late cancellation as too_late.
- Durable retry schedules store originating attempt, next attempt number, due/deadline timestamps, capability name/version, idempotency key, capability evidence and immutable policy snapshot.
- Retry scheduling atomically finalises the failed attempt and evaluation, returns the task to pending and persists the schedule.
- Claims cannot start before due time, after the deadline, beyond the configured attempt ceiling, or after schedule cancellation/expiry. Due claims consume the schedule and link it to a new fenced attempt atomically.
- A cancellation request against a pending scheduled retry cancels and terminalises the task with an evaluation. An expired retry deadline also terminalises the task with a retry-expired evaluation.
- Authenticated read-only due-retry scan and retry-expiry maintenance routes are available; they inspect/expire schedules but do not dispatch task execution.
- Tests cover retry policy validation, capability evidence, fake-provider duplicate suppression, cancellation idempotency/races/fencing, restart persistence, expired/late requests, retry schedule eligibility, due-time gating, concurrent claims, attempt ceilings, expiry, terminal outcomes and scheduled-retry cancellation.

Current limits:
- The capability runtime is deliberately narrow, not a general plugin system. The current one-step route can execute only the five application-owned built-in handlers described above; there is no generic planner-to-handler binding, dynamic plugin loading or unattended scheduler/dispatcher.
- The bounded local executor has a cooperative 30-second monotonic per-attempt deadline and a 128-node AST complexity cap. There is no hard termination mechanism for uninterruptible work or future external capabilities.
- The existing local task executor remains single-attempt and is not opted in; retry scheduling is an internal primitive only.
- The current Crossref read-only handler performs bounded network I/O in-process. Its transport timeout is not a hard process-kill boundary; do not add further network or credential-bearing handlers until isolation, destination controls and resource termination are proven.
- The capability execution route is manually invoked one step at a time. It is not an autonomous scheduler and must not be described as one.
- Shared API-key authentication and caller-supplied actor labels are not verified per-user identity or RBAC.

At code head `5fda244649fd32b6d6a2875c8402ae35a2c0d262`, both [PR workflow](https://github.com/quickchefbooking-ship-it/Project-atlas-/actions/runs/43402285254) and [push workflow](https://github.com/quickchefbooking-ship-it/Project-atlas-/actions/runs/43402277024) passed **211 tests** with one non-blocking Starlette/AnyIO deprecation warning. Coverage also includes bounded task intake and validation responses that omit request values.

Acceptance gates:
- Tests prove retry limits are enforced under concurrent requests and due-time claims.
- Cancellation is deterministic at documented safe points and produces a durable audit event.
- Duplicate execution is prevented by idempotency keys and fencing for any future opted-in capability.
- Non-idempotent or uncertain external actions are never automatically retried.
- Process restart preserves retry/cancellation state and immutable schedule snapshots.
- Every acceptance-matrix row in the Phase 2 design is covered before runtime Phase 3 orchestration or capability execution begins.

## Phase 3 — Professor capability registry and specialist arms

**Status: registry, pinned schema validation and a narrow tenant-scoped execution vertical slice implemented; general specialist routing and isolated external adapters remain planned.**

Deliverables:
- Delivered: application-owned, immutable, versioned capability definitions with input/output schema metadata, scopes, risk class, side-effect declaration, timeout, approval policy and retry-contract matching. Remote schema references and mutable schema metadata are rejected.
- Delivered: Draft 2020-12 JSON Schema syntax checks at registration and bounded runtime input/output validation; payloads are finite JSON objects with a 64-KiB cap and errors do not echo untrusted values.
- Delivered: fixed application-owned handler bindings and a tenant-scoped one-step execution route protected by verified identity, `plans:execute`, registered capability scopes, plan readiness and exact capability version.
- Delivered vertical slice: bounded local arithmetic; read-only Crossref scholarly search; evidence bundling, deterministic evidence evaluation and Professor report generation. No task-supplied handler registration or arbitrary code execution.
- Delivered: a separately enforced, process-wide capability execution kill switch. It defaults off and only enables when `ATLAS_CAPABILITY_EXECUTION_ENABLED=true`; the route checks it on every request before plan/storage/handler work. Tests prove fail-closed configuration and zero handler calls when disabled.
- Delivered in the current draft: tenant-scoped append-only execution audit reservations. A committed reservation records verified principal, tenant, plan/step, capability version, attempt/fencing identifiers and a canonical input digest before `runtime.execute` is called. Handler outcome is appended separately with an output digest or bounded error code; raw inputs/outputs are not copied into the audit log. A reservation-write failure returns a fail-closed storage error and the handler is not invoked. CI review remains pending.
- Delivered in the current draft: `_get_json` enforces exact HTTPS origins and resource paths for Crossref, GitHub and Hugging Face public metadata endpoints, in addition to rejecting redirects and bounding response size/time. This is application-layer destination validation only, not network egress isolation.
- Delivered in the current draft: deterministic evidence excerpt traceability. It hashes a supplied source snapshot, checks exact excerpt presence, optionally detects source-version drift and records attributed reviewer metadata. It explicitly does not infer whether the excerpt supports a claim or assess source credibility; see `docs/professor-evidence-traceability.md`.
- Delivered in a follow-on draft: source excerpt traceability resolves source text, URI and digest by persisted document ID, requires an approved/reviewed source record, recomputes the digest, and rejects caller-supplied source substitution. SQLite triggers prevent source snapshot content/provenance edits and deletion. This is not tamper-proof against database administrators and is not yet integrated into the authenticated Professor research/report route; source-ingestion reviewer labels remain unverified metadata.
- Existing authenticated reviewer workflow: the tenant evidence-review route derives reviewer attribution from the verified principal, requires the `evidence:review` scope, rejects client-supplied reviewer IDs and stores tenant-scoped append-only review revisions. The current draft strengthens the regression test to assert the exact issuer/subject-derived reviewer fingerprint.
- Delivered in the current follow-on draft: deterministic HTML locator resolution for approved stored `text/html` source snapshots. It excludes script/style/template content, verifies the stored source digest, resolves exact excerpts to semantic block paths, and reports ambiguous or missing matches without guessing. It does not fetch websites, execute browser code, prove claim support or resolve PDF coordinates. This helper is not yet integrated into the authenticated Professor research/report route.
- Remaining: integrate approved-source lookup and HTML locator resolution with tenant ownership checks in the authenticated review route; derive source-ingestion approval identity from the verified principal; add PDF locator support only after parser dependency/security review; assess source quality/retractions and independent corroboration. See `docs/professor-evidence-traceability.md`. Move the existing network-capable Crossref adapter behind a separately isolated worker before expanding network access; see `docs/professor-isolated-research-worker.md`.
- Add specialist arms incrementally: knowledge/research, media, HR/operations and communications drafts.
- Keep email sending, social publishing, payments, trading, purchasing and deletion disabled or approval-gated until later security gates pass.

Acceptance gates:
- Contract tests cover every registered capability and reject malformed inputs or undeclared side effects.
- The orchestrator cannot escalate a capability's scopes or access another arm's credentials.
- Risk classification and human approval are enforced server-side, not just in the UI.
- Capability version and evidence are recorded for every task attempt.

## Phase 4 — Memory and learning governance

**Status: planned.**

Deliverables:
- Separate task context, episodic execution history, source documents and reusable validated lessons.
- Require evidence, provenance and verified reviewer identity before lesson promotion.
- Add review, rejection, correction, supersession and rollback history.
- Scope memory to the correct user or organisation; apply retention and deletion rules.
- Improve retrieval quality only with measurable relevance tests; keep lexical and semantic retrieval claims distinct.
- Treat retrieved content as untrusted data, never as instructions or policy.

Acceptance gates:
- Unapproved, rejected or superseded material cannot enter approved retrieval.
- Every reusable lesson has provenance, validation history and reviewer attribution.
- Tests cover prompt injection, duplicate content, stale sources, conflicting evidence and tenant boundaries.
- A lesson can be corrected or withdrawn without erasing the audit history.

## Phase 5 — Identity, security and release readiness

**Status: planned.**

Deliverables:
- Verified user identity, role-based access control and tenant isolation.
- Per-user/per-tenant delegated credentials with least privilege and a secrets manager.
- Append-only audit events, rate limits, request budgets, monitoring and incident response.
- Tested backup/restore, migration, retention and deletion procedures.
- Threat modelling, dependency/supply-chain review and independent security testing.
- Evidence mapping for UK GDPR, Cyber Essentials, ISO 27001 and SOC 2 readiness where applicable; do not claim certification or compliance without independent evidence.
- A release candidate review with documented rollback and operational ownership.

Acceptance gates:
- Independent security review has no unresolved critical/high findings.
- Tenant isolation, authentication, authorization, audit and data lifecycle tests pass.
- Backups and restore are demonstrated, not merely configured.
- No unapproved external write can occur.
- Separate human approval is obtained before any merge, deployment or production release.

## Immediate next actions

1. Complete a focused review of the Phase 1/2 combined diff, especially cancellation-versus-completion ordering, retry due/deadline claims, expired lease recovery, and task/evaluation/attempt transaction boundaries.
2. Keep the shared API-key limitation explicit: actor labels and capability evidence references are not verified identity or independent proof; this prototype is not suitable for public multi-user use.
3. Keep the existing capability catalogue application-owned and closed to task registration. Bind evidence excerpts to approved immutable source snapshots, authenticate reviewer identity, resolve source locators and assess source quality/retractions before calling any evidence independently verified. Continue proving identity/tenant/scope enforcement and output validation on the exact execution path, and complete review of the pre-dispatch audit reservation.
   - Tenant-owned approved source snapshots now have a draft repository/schema foundation: compound tenant/document lookup, pending-by-default review, immutable content, and server-derived reviewer attribution input. Next expose authenticated tenant ingestion/approval routes and integrate the tenant-owned resolver with evidence review. The legacy global source store is not a tenant boundary.
4. Implement the isolated worker only after an approved host/runtime is available. Use `docs/professor-isolated-research-worker.md` as the gate: a child process alone is not a sandbox, and no in-process fallback is allowed. Do not add network-capable or credential-bearing handlers until OS-enforced egress/resource/process controls pass integration tests.
5. Design an owner-authenticated operational emergency-stop/override control only after identity and audit foundations are ready. It must stop new dispatches and safely signal/cancel in-flight isolated workers; the existing environment kill switch does not do this.
6. Only after registry verification is enforceable, design a disabled-by-default due-work scheduler with explicit operational controls and restart/concurrency tests. Existing due-time claim gates remain manual and do not auto-dispatch work.
7. Revisit per-attempt timeout semantics only with an executor that can stop safely or prove side-effect reconciliation; do not imply a thread timeout can undo work.
8. Continue persistent-memory/evaluation regression coverage and record exact PR/push CI evidence after each meaningful change. Do not enable runtime capability invocation or specialist arms until the Phase 2 gates and Phase 3 security/contract gates pass.

## Current project references

- Repository: https://github.com/quickchefbooking-ship-it/Project-atlas-
- Recovery PR #1: https://github.com/quickchefbooking-ship-it/Project-atlas-/pull/1
- Phase 1 design: docs/task-crash-recovery-phase-1.md
- Working branch: atlas/repair-baseline-2026-11-12
- Production/main remains unchanged.
