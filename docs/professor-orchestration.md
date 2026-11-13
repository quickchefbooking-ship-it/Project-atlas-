# Professor orchestration blueprint

**Status:** design guidance for the existing AtlasOnePro Professor prototype. This document does not enable integrations, autonomous actions, paid services or deployment.

## 1. Verified starting point

The current repository is an early, local Python prototype:

- FastAPI exposes task, evaluation, lesson, proposal and media routes.
- Task execution is synchronous through TaskAPI and the local arithmetic executor.
- The evaluator applies deterministic success criteria.
- SQLite persists tasks, evaluation records, lessons and improvement proposals.
- Task attempts and evaluation outcomes are recorded.
- Lesson retrieval excludes records unless they are marked validated. Failed-task lessons are currently saved as unvalidated, and there is not yet a complete evidence-based lesson-validation workflow.
- Proposal review supports approval or rejection. The proposal action that marks a proposal tested is deliberately disabled until real test evidence can be produced.
- Protected API routes use a shared API key by default. This is a development access control, not user identity, role-based access or tenant isolation.
- Media generation is constrained to its configured output directory.
- The local executor supports basic arithmetic only. It is not a general-purpose agent.

These limits are intentional. The Professor must not be described as a fully autonomous or self-improving system yet.

## 2. The octopus model

The Professor should be the single orchestration authority. Specialist arms should be capabilities registered with the Professor, not independent agents with unrestricted credentials.

Examples of future arms include:

- **Knowledge and research:** retrieve approved sources and return cited findings.
- **HR and operations:** read approved records, draft plans and surface risks.
- **Media studio:** generate or edit media in an isolated workspace.
- **Communications:** read messages and prepare drafts; sending remains approval-gated.
- **Finance and markets:** retrieve read-only account or market data; trading and transfers remain disabled unless separately authorised.
- **Social publishing:** prepare content and previews; publication remains approval-gated.

Each arm must expose a narrow, typed contract. It must not receive every other arm's credentials or unrestricted access to the whole system.

## 3. Target request lifecycle

1. **Authenticate:** establish the caller, organisation/tenant and permitted scopes. A shared API key is only a temporary prototype control.
2. **Intake:** validate the request and convert it into a structured task with an explicit objective and measurable acceptance criteria.
3. **Classify risk:** label the requested work as read-only, local computation, draft creation or external side effect.
4. **Plan:** produce a structured plan with named capabilities, inputs, dependencies, expected outputs, deadlines and budgets. Do not generate arbitrary shell commands or executable code as a plan.
5. **Check policy:** reject disallowed actions and require explicit approval before sending, publishing, purchasing, trading, deleting, changing permissions or deploying.
6. **Execute:** run one approved capability at a time through a controlled worker. Persist each state transition and result.
7. **Evaluate:** compare the result against the task's measurable criteria. Store the evidence and the evaluator version.
8. **Learn cautiously:** record outcomes with provenance. Reuse only lessons that have passed a separate validation process.
9. **Report:** return the result, evidence, unresolved items and any approval still required.

A task should move through explicit states such as **pending**, **planned**, **awaiting_approval**, **running**, **succeeded**, **failed** and **cancelled**. State transitions must be validated rather than assigned freely.

## 4. Capability contract

A future capability registry should require each arm to declare:

| Contract field | Purpose |
| --- | --- |
| Name and version | Stable identity and reproducibility |
| Input/output schema | Validate data at the boundary |
| Risk class | Read-only, local write, external write or privileged |
| Required scopes | Least-privilege access |
| Side-effect declaration | Identify whether the action changes an external system |
| Timeout and resource budget | Bound execution |
| Idempotency support | Prevent duplicate writes on retries |
| Approval policy | Define when human confirmation is mandatory |
| Audit metadata | Record caller, task, capability version and outcome |

The orchestrator should reject unregistered capabilities and inputs that do not match their schemas. A capability must not be able to silently escalate its scopes.

## 5. Memory and evaluation

Use separate memory layers:

- **Task context:** short-lived information needed for one run.
- **Episodic records:** durable task inputs, outputs, evaluation evidence, timestamps and capability versions.
- **Validated lessons:** reusable guidance promoted only after a defined review process.

A failed task is evidence of a failure, not proof that the proposed lesson is correct. Repeated outcomes, independent checks and human review should be required before promotion. Validation must be attributable and reversible, and records should be scoped to the correct user or organisation.

The current SQLite schema is suitable only for the prototype. Before multi-user use, add tenant scoping, provenance and validation history, retention controls, migration tests, backups and an append-only audit trail.

## 6. Security and integration rules

- Keep integrations read-only by default.
- Use per-user or per-tenant delegated credentials with minimum scopes; never share one arm's token with another.
- Store secrets in a dedicated secrets manager, not in task records, prompts, logs or source control.
- Require explicit approval for external side effects. Approval must be bound to the exact action, target, parameters and expiry.
- Treat the current approved_by value as caller-supplied audit metadata, not verified identity.
- Use an identity provider and role-based authorisation before commercial multi-user use.
- Enforce tenant isolation, rate limits, request-size limits, timeouts and audit logging.
- Validate external URLs and downloaded content; prevent SSRF and unsafe file writes.
- Do not execute untrusted proposal code. A temporary directory is not an operating-system sandbox.
- Do not allow self-modifying code, autonomous production deployment, live trading or automatic outbound messaging in this prototype.

## 7. Delivery phases

### Phase A — Reliable core

Complete task state transitions, evaluation persistence, deterministic executor boundaries, migration tests, error handling and a dependable CI gate. Keep the current recovery PR isolated until its full test suite and review are satisfactory.

### Phase B — Orchestration foundation

Introduce a persisted plan model, capability registry, dependency-aware execution, idempotency keys, bounded retries, cancellation and per-step audit events. Start with local, read-only capabilities.

### Phase C — Specialist arms

Add one arm at a time behind typed adapters and contract tests. Begin with low-risk read-only research and internal media workflows. Keep email, calendar, messaging and social operations in draft/read-only mode initially.

### Phase D — Controlled external actions

Only after identity, tenant isolation, audit and security review are in place should narrowly scoped write actions be considered. Require action-specific human approval and a reversible recovery plan where possible.

### Phase E — Commercial readiness

Complete threat modelling, independent security testing, dependency and supply-chain controls, incident response, backups, retention/deletion workflows and the relevant compliance evidence. This blueprint is not itself evidence of SOC 2, ISO 27001, Cyber Essentials or UK GDPR compliance.

## 8. Release gates

A phase is not complete because code exists. It is complete only when:

- its tests pass in CI;
- failure and retry behaviour are tested;
- access scopes and side effects are explicit;
- audit records explain what happened and why;
- secrets and personal data are not exposed;
- no unapproved external write can occur;
- documentation matches the behaviour actually shipped.

Until those gates are met, keep changes on the recovery branch and do not merge or deploy.
