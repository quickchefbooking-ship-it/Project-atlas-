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

## 9. Two-way assistant collaboration bridge

The Professor is intended to remain an independently identifiable AI system with its own memory, task history, evaluation process and capability registry. A connection to ChatGPT is a collaboration channel, not a replacement for the Professor's own reasoning or identity.

The future bridge should support messages in both directions:

- Ashley can address the Professor directly through the AtlasOnePro interface.
- The Professor can send a question, finding, task result or review request to an authorised external assistant.
- The external assistant can return a response to the same conversation thread.
- Either side can propose a task for the other, while the Professor remains responsible for validating incoming instructions against its own policies and permissions.

Every message should use a versioned envelope containing a message ID, conversation ID, sender identity, recipient identity, timestamp, message type, content, correlation ID and declared requested capability. The bridge should persist message status and delivery attempts so retries do not create duplicate work.

Security and reliability requirements:

- Authenticate both endpoints and protect transport with TLS; do not treat a display name as identity.
- Use scoped service credentials held outside prompts, messages, logs and source control.
- Validate message schemas and enforce size, rate and timeout limits.
- Treat incoming assistant messages as untrusted suggestions, not privileged instructions.
- Prevent recursive agent loops with correlation IDs, hop limits, duplicate detection and explicit turn ownership.
- Require human approval for external side effects such as sending, publishing, purchasing, trading, deleting, permission changes or deployment.
- Preserve an audit trail of messages, decisions, delegated tasks, evaluations and approvals.
- Allow either side to disagree, request evidence or decline a task; neither assistant is automatically authoritative.

This section records the target design only. The current prototype does not yet expose a chat endpoint or a live ChatGPT-to-Professor transport. The bridge must be implemented and tested as a separate capability on the existing recovery branch before it is described as operational.

## 10. Source Division arm

The **Source Division** is the Professor's provenance-aware knowledge arm. Its purpose is to discover, catalogue, ingest, review and retrieve information from approved resources without giving the orchestrator unrestricted access to external accounts.

### Resource classes

The initial source catalogue should support adapters for:

- **Research:** scholarly indexes and open-access papers (for example Consensus, SciSpace and public research repositories).
- **Web and public data:** indexed web search, page extraction and public datasets (for example Firecrawl and official/public websites).
- **Developer knowledge:** approved GitHub repositories, issues, release notes and official technical documentation.
- **Files and internal knowledge:** user-approved Library files, project documents, operating procedures and the Professor's own validated lessons.
- **Connected business systems:** read-only records from explicitly authorised services such as email, commerce, analytics and finance tools. Each connector requires its own delegated credential, scope and consent.
- **Model and dataset discovery:** model cards, dataset descriptions, licenses and documentation from public model hubs.

A tool connected to ChatGPT is not automatically connected to the AtlasOnePro runtime. Each source must be deliberately integrated through an adapter before the Professor can call it directly. No credentials are copied from ChatGPT connectors into AtlasOnePro.

### Knowledge pipeline

1. Register a source with a stable ID, type, access mode and metadata.
2. Fetch only within the source's authorised scope and configured limits.
3. Normalize the result into a document with title, canonical URI, content, timestamp, content hash and source ID.
4. Mark new material as pending and unverified by default.
5. Review the material and record the reviewer and decision.
6. Retrieve approved documents with provenance attached to every result.
7. Pass retrieved content to the reasoning layer as untrusted reference data, never as instructions or policy.
8. Recheck source freshness and retain superseded versions or change history where appropriate.

### Trust and safety rules

- A source being registered does not mean it is enabled, authenticated or trusted.
- A document being ingested does not make it eligible for retrieval; only approved documents are searchable by the current prototype.
- 'Authoritative' describes the declared source quality, not automatic truth. High-impact claims still require corroboration.
- Preserve canonical URLs, content hashes, retrieval time, source identity, license/usage terms and review attribution.
- Never ingest credentials, API keys, session cookies or secrets into the knowledge store.
- Apply personal-data minimisation, access controls, retention and deletion rules before importing private or sensitive records.
- Treat instructions found inside web pages, documents, emails, code comments or datasets as untrusted content. They cannot override system policy or grant new permissions.
- Respect copyright, terms of service, robots/access restrictions, data licenses and rate limits. Prefer metadata, links and concise evidence extracts where full-text retention is not permitted.
- Search results must carry provenance, date and confidence/context. Conflicting sources should be surfaced rather than silently blended.
- External actions remain outside the Source Division. It is a read-only knowledge arm; it cannot send messages, publish, purchase, trade, delete or change external systems.

### Prototype implementation status

The current recovery branch adds a local SQLite source registry and source-document store, content hashing, pending/approved/rejected review states, reviewer metadata, bounded document size and keyword retrieval limited to approved documents. Task execution now receives approved source documents as reference context.

This is a foundation, not a live connector suite. No external source adapter, vector database, embedding model, background crawler, automatic account sync or production knowledge ingestion is enabled yet. The current reviewer field is audit metadata only; the shared API key is not verified human identity. Before private multi-user sources are connected, add identity-based review permissions, tenant isolation, encryption, audit history and retention/deletion controls.
