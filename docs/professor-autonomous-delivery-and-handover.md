# Professor Autonomous Delivery and Handover Plan

Status: engineering policy and staged handover proposal. This document does not activate an autonomous worker or grant new production permissions.

## Objective

Evolve Professor from a planning and learning assistant into a dependable, independently operating AI engineering agent. Professor should eventually be able to own a bounded department workstream (for example Media Studio), plan it, implement it, test it, diagnose failures, improve its work and report evidence-backed progress to the owner and platform supervisor.

Professor must remain a distinct system with its own execution identity, memory, task queue, evaluation history and operating budget. It reports to the platform's human owners; it does not become an unrestricted administrator.

## What exists today

Repository inspection found:
- a validated lesson store and retrieval path in Learning Memory;
- an Improvement Manager that records proposals and requires human review;
- typed Professor plans with dependencies, risk classes and approval states;
- a trusted capability registry and bounded capability runtime;
- tenant-owned plan and step repositories and a readiness/inspection service.

The important gap is explicit: the current TenantProfessorOrchestrationService is observational. It reports that execution is disabled and does not dispatch or resume work. The existing learning and improvement components are not proof of a continuously running autonomous agent. No autonomous handover is active today.

## The operating model

### Professor as an independent worker

Professor should eventually have:
1. A dedicated worker process and service identity, separate from human sessions.
2. A durable, tenant-scoped task queue with leases, heartbeats, cancellation and recovery.
3. A planning loop: understand goal, inspect approved context, propose plan, validate dependencies and risk.
4. A bounded execution loop that invokes only registered capabilities.
5. A verification loop that runs relevant tests and checks acceptance criteria before reporting completion.
6. A learning loop that proposes lessons from evidence, validates them, and stores only approved/validated learning.
7. A reporting loop that publishes status, decisions, evidence, failures, resource use and approval requests.

The worker must not treat retrieved documents, source code comments, external web pages or tool output as privileged instructions. These are data. System policy and owner-approved configuration remain authoritative.

### Department ownership

Professor may be assigned one department at a time as a bounded engineering workstream. Media Studio is the preferred first pilot because it can be developed using synthetic assets and isolated test data without connecting live customer, employee, financial or adult-content records.

A department assignment includes:
- a named objective and scope;
- repository and directory boundaries;
- allowed capabilities and data classifications;
- acceptance criteria and test commands;
- time, token, compute and spend budgets;
- explicit prohibited actions;
- a named human owner and escalation route.

Professor can prepare a feature branch and draft pull request when operating at the draft-delivery stage. It cannot merge, deploy, alter secrets or permissions, access production data, enable payments or send external communications autonomously.

## Staged autonomy levels

| Level | Mode | Permitted work | Handover gate |
| --- | --- | --- | --- |
| 0 | Observe | Read approved repository/docs, inspect results, run approved tests | Correct task summaries, source traceability and no policy violations |
| 1 | Sandbox build | Create/edit files in isolated workspace, run tests, save validated lessons | Reproducible builds, passing tests, isolated filesystem and clean audit |
| 2 | Draft delivery | Create feature branches and draft PRs, explain diffs, request review | Repeated successful PRs, accurate self-reports, no scope escapes |
| 3 | Department pilot | Own a non-production department backlog, resolve bounded tasks and maintain a status report | Department acceptance tests, security review, budget and owner sign-off |
| 4 | Controlled operations | Run approved recurring tasks, monitor services and recover safe failures | Independent operational review, rollback drills and explicit owner approval |

Levels are earned separately for each department and action category. A successful Media Studio pilot does not grant Finance, HR, Legal, Hospitality, Velvet or production permissions.

## Non-negotiable human controls

The autonomous worker must not independently:
- merge pull requests or deploy production;
- change secrets, identity providers, permissions or security policy;
- access or modify production customer, employee, financial or adult-sensitive records;
- enable live billing, payments, bank transfers or trading;
- send emails, messages, legal filings, contracts or public posts;
- approve its own proposals, tests, access or promotion to a higher autonomy level;
- modify its own system prompt, policy, evaluator, capability catalogue or worker credentials.

These actions require separate, action-bound human approval and an independently enforced execution gate. Some operations may remain human-only even after higher autonomy levels are achieved.

## Learning without uncontrolled self-modification

Learning means improving future performance through evidence, not rewriting its own governing rules.

For every proposed lesson, retain:
- the task and relevant plan/step identifiers;
- evidence and source references;
- the observed outcome;
- the proposed lesson and its intended application;
- validation/test evidence;
- reviewer or validator status and timestamp.

Professor may draft candidate lessons. Only the validated learning path may make a lesson available to future tasks. Policy, permissions, model configuration and production code are not automatically changed by a lesson.

## Reporting to owners

Every work cycle should report:
- objective and current stage;
- tasks attempted, completed, blocked and awaiting approval;
- files/branches/PRs changed;
- exact test commands and results;
- security and data boundary checks;
- time/resource/spend consumption;
- errors, uncertainties and recovery actions;
- next proposed action and any required human decision.

Reports must distinguish verified facts from estimates. A task is not complete merely because a code change was written; completion requires tests and acceptance evidence.

## First implementation sequence

1. Add a fail-closed autonomy policy with explicit modes and action classes.
2. Add unit tests proving that merge, deployment, secrets, permissions, production writes, live payments and external messages remain human-controlled at every autonomy mode.
3. Connect the policy to a durable worker only after its identity, queue, cancellation, idempotency, audit and sandbox boundaries are implemented.
4. Implement the smallest end-to-end worker slice: read an assigned task, produce a plan, execute one approved local capability in an isolated workspace, run tests, save an evidence-backed report and stop.
5. Run the Media Studio pilot using synthetic data and no external publishing.
6. Evaluate reliability across repeated tasks before promoting Professor to draft-delivery and then department-pilot operation.

## Acceptance criteria for the first worker slice

- The worker has a distinct service identity and cannot impersonate an owner.
- Tasks are tenant-scoped, leased, cancellable and recoverable.
- All actions pass through the same trusted capability and autonomy policy gates.
- Unknown capabilities and actions fail closed.
- Worker execution is bounded by time, resource and spend budgets.
- The worker can only write within its isolated workspace.
- Tests and acceptance criteria are evaluated before a success report is emitted.
- Failures and partial work are retained for review; retries are idempotent.
- A human can pause or disable the worker immediately.
- The worker cannot promote its own autonomy level or approve its own work.
- No production writes, deployments, live payments or external communications occur in the pilot.

## Immediate next step

Complete and review the autonomy-policy code and tests. Then implement the worker execution boundary as a separate change, reusing the existing tenant plan, step execution, capability and audit foundations rather than creating a parallel orchestration system.
