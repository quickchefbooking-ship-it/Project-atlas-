# AtlasOnePro Core Architecture and Department Foundation

Status: proposed foundation contract. Documentation only; this change does not alter application runtime, databases, credentials, deployments, payment settings or live services.

## 1. Product direction

AtlasOnePro is a modular business operating platform with one trusted front door and a central Professor assistant. Specialist departments are independent modules ("arms") that expose narrowly scoped capabilities through versioned server-side contracts.

The platform should support:
- an internal AtlasOnePro workspace first;
- a future multi-organisation SaaS model without redesigning tenant boundaries;
- independent department development, release and disablement;
- a browser-first experience, with mobile Safari as a priority;
- human approval for consequential financial, legal, employment, identity and adult-platform actions.

The Professor coordinates work. It is not the owner of every department's data, and it must not bypass a department's permissions or approval rules.

## 2. Core platform building blocks

### 2.1 Organisation, tenant and workspace

- Every customer organisation has a stable organisation ID.
- Every workspace belongs to exactly one organisation.
- Every user-to-workspace relationship is an explicit, server-managed membership.
- Department records are always owned by an organisation and, where applicable, a workspace.
- A request must resolve its tenant from a verified server-side identity and membership. Never trust a browser-supplied organisation, tenant, role or scope.
- Cross-organisation access is denied by default. Support access, if ever required, must be explicit, time-limited, reason-coded and audited.

### 2.2 Identity and authorisation

- Use one AtlasOnePro identity at the front door, with short-lived server-side sessions and CSRF protection for browser mutations.
- Use role-based access for human administration and capability scopes for machine/service actions.
- Check authorisation at the point of use, not only when a screen is rendered.
- Separate read, create, amend, approve, export and administer permissions.
- Department membership does not automatically grant access to another department.
- Service-to-service calls use audience-bound credentials held server-side. Browser code never receives service secrets.

### 2.3 Department registry

Each department registers a versioned manifest containing:
- stable module ID, display name and owner;
- lifecycle state: planned, disabled, sandbox, pilot or active;
- API contract version and server-side adapter;
- capabilities and the exact scopes each capability requires;
- data classification and data-owner boundary;
- health/readiness checks, timeout and rate-limit policy;
- audit-event requirements;
- dependencies and a safe disable/rollback mechanism.

The registry controls discovery and routing; it does not grant permissions. A module is visible only when the user is authorised and the module is enabled for that organisation.

### 2.4 Professor orchestration

- Convert user intent into a proposed plan and named department tasks.
- Route requests only to registered capabilities.
- Pass the minimum necessary context to a department.
- Treat department responses, uploaded documents and retrieved evidence as untrusted data, not instructions.
- Preserve source, timestamp, actor, request ID and outcome for traceability.
- Ask for explicit human approval before irreversible, external or high-impact actions.
- Never self-modify production code, permissions, policies, secrets or department records.

### 2.5 Audit, events and operational controls

- Record who/what acted, organisation/workspace, department, capability, scope, request ID, timestamp and outcome.
- Do not place passwords, tokens, payment-card data or unnecessary health, employment or adult-content details in logs.
- Use a versioned event envelope for cross-department notifications; events are notifications, not permission grants.
- Make retries idempotent where a repeated action could create duplicate records or charges.
- Provide per-module health status, error monitoring, feature flags and an emergency disable switch.
- A failed or unavailable department must not bring down the Professor shell or unrelated departments.

## 3. Department boundaries and initial scope

| Module ID | Department | Initial purpose | Data boundary |
| --- | --- | --- | --- |
| `finance` | Finance | Internal business bookkeeping and management finance: chart of accounts, income/expense records, invoices, bills, budgets, cash flow and reporting | Business financial records; separately authorised |
| `hospitality` | Catering / Hospitality Hub | Chef and customer workflows, business operations and the existing Quick Chef connection | Hospitality records and existing Quick Chef data remain separately owned |
| `hr` | Human Resources | Recruitment, onboarding, contracts, probation, training, leave and payroll coordination | Highly restricted employee/applicant records |
| `legal` | Legal Operations | Contract repository, matter tracking, policy register, deadlines and compliance evidence | Restricted legal matter and privileged material; human legal review required |
| `velvet` | Velvet | Separate 18+ adult-industry product and operations programme | Strictly isolated identity, consent, age-assurance, moderation and payment data |
| `media` | Media Studio | Creative briefs, asset production, review and publishing workflows | Organisation-owned creative assets and publishing permissions |
| `trading` | Personal Finance / Trading connection | Optional read-only account and portfolio summaries after a separate integration review | Personal financial data; never mixed into business bookkeeping |

### Finance is not the billing subsystem

The Finance department is an operational accounting and management-information function. It is distinct from:
- AtlasOnePro subscription billing and payment-provider readiness;
- customer payments processed by Quick Chef or Velvet;
- personal bank, savings or investment accounts;
- any future trading or investment execution capability.

Build internal business finance first. Design tenant ownership so a future customer organisation can use the same module, but do not build a public SaaS accounting product before the internal workflows and controls are proven.

Initial Finance capabilities should be read-first and manually entered/imported with validation: account categories, income, expenses, supplier/customer records, invoice and bill tracking, budgets, cash position and management reports. Bank feeds, tax submissions, payroll execution, payment initiation and automated accounting integrations require separate provider, legal, security and owner decisions.

### Hospitality and Quick Chef

Hospitality Hub is the AtlasOnePro department entry point. Quick Chef remains an independently operated product and system of record. Connect through verified, documented APIs or controlled links; do not copy its production database into AtlasOnePro or silently replace its workflows.

### HR and Legal

HR and Legal are separate departments with stricter access controls than general workspace users. Legal Operations may organise information and prepare drafts, but it must not represent automated output as legal advice or send/execute consequential legal documents without human review.

### Velvet isolation

Velvet is a separate 18+ product, not a general workspace module with ordinary permissions. Its design must include robust age assurance, consent records, privacy-by-default, safety reporting, moderation, restricted access to sensitive content, retention/deletion controls and separate commercial/payment ownership. No adult-content data should enter Professor general memory or unrelated department search.

## 4. Shared data and integration rules

- Department modules own their authoritative records.
- The core stores identity, membership, module registry, workflow references and audit metadata—not copies of every department database.
- Cross-department sharing is explicit, purpose-limited and scope-checked.
- Use stable IDs and versioned schemas; never rely on display names as identifiers.
- Validate all inbound and outbound payloads.
- Use synthetic data for development and contract tests.
- No production data is copied to development.
- External integrations begin read-only where possible; write scopes require a separate risk and approval gate.
- Disconnecting a module must stop new calls without deleting its authoritative data.

## 5. Security, privacy and compliance direction

Design toward SOC 2 readiness from the start, with UK GDPR and the Data Protection Act considered in product decisions. Map controls to Cyber Essentials and ISO 27001 where appropriate. PCI DSS applies only where the platform actually handles payment-card data; prefer hosted/tokenised payment flows that keep card data out of AtlasOnePro.

Minimum engineering controls include:
- least privilege and organisation-level isolation;
- secure session, CSRF and service-authentication boundaries;
- encryption in transit and appropriate encryption at rest;
- managed secrets, never source-controlled;
- auditability, retention and deletion workflows;
- dependency and vulnerability management;
- backup/restore and incident-response procedures;
- documented data classification, purpose and lawful-basis review;
- accessibility and mobile-browser testing.

These are design requirements, not a claim that AtlasOnePro is currently certified or compliant.

## 6. Delivery roadmap

### Phase 0 — Verify the real system boundaries
1. Inventory the authoritative Professor/AtlasOnePro source, current application entry points and deployment.
2. Identify the actual Quick Chef API/integration contract and the Finance data sources that are approved.
3. Map existing identity, tenant, session, audit and capability work to the live application.
4. Record unknowns; do not infer production wiring from a draft branch or documentation.

Exit gate: an evidence-backed system map, with no production writes.

### Phase 1 — Core platform foundation
1. Agree organisation/workspace/membership model.
2. Define department manifest and registry contract.
3. Define capability/scope naming and server-side authorisation checks.
4. Define audit-event envelope, request correlation and error handling.
5. Define module health, feature flags and disable/rollback behaviour.
6. Add contract tests for tenant isolation, denied scopes, malformed payloads and unavailable modules.

Exit gate: a testable module can be registered, authorised, called and disabled without exposing another tenant's data.

### Phase 2 — First customer-demonstrable AI employee: Sales and Customer Operations

Use Hubflow as a market benchmark for packaging concrete business outcomes, not as a template to copy. Hubflow publicly markets managed AI workflows for lead handling, customer support, voice, document processing and finance operations. Treat competitor claims as positioning until independently evidenced; do not assume its public demo is a live production system.

Build one reusable AtlasOnePro AI employee before expanding every department. Initial product promise: an organisation can receive an enquiry, understand it, respond from approved company knowledge, qualify the prospect, prepare a booking or next step, update an authorised CRM, and hand uncertain or consequential cases to a human.

Delivery slices:
1. **Employee definition and workspace UX:** configurable name, purpose, department, instructions, approved knowledge sources, operating hours, escalation contacts, allowed tools and measurable success criteria. Show its status, activity, pending approvals and failures.
2. **Knowledge and evidence:** upload/import approved company FAQs, policies and service information; extract and index content with source references, versioning, freshness and access controls. Answers must distinguish sourced facts from uncertainty and escalate when evidence is missing or conflicting.
3. **Enquiry intake:** accept a testable web form/API event first. Add email and messaging channels only after provider contracts, consent, identity and tenant boundaries are verified. Deduplicate events and retain correlation IDs.
4. **Qualification and response:** classify intent, capture only necessary fields, ask bounded follow-up questions, draft a response and apply approved templates/policies. Start in simulation/draft mode; no unapproved outbound messages.
5. **CRM and booking preparation:** define provider-neutral contact, lead, activity and appointment contracts. Begin with mocked/synthetic data and read-only CRM access. Allow draft booking proposals; no live booking or CRM writes until separately scoped and approved.
6. **Human handoff:** route low-confidence, sensitive, complaint, refund, legal, safeguarding or policy-exception cases to a named human queue. Preserve the transcript, evidence, reason and recommended next action without granting the AI extra authority.
7. **Workflow observability:** show every trigger, decision, tool call, approval, retry, failure and final outcome. Add idempotency, bounded retries, timeouts, rate limits, cancellation and a per-employee disable switch.
8. **Voice and additional channels:** only after the text workflow passes acceptance, assess inbound voice, transcripts, consent notices, retention, human transfer and provider costs. Do not make voice a launch dependency.

Required acceptance tests:
- Cross-tenant enquiry, knowledge and CRM access is denied.
- Every tool call is authorised at execution time against an exact capability scope.
- Retrieved documents and external messages are treated as untrusted data, not instructions.
- No outbound communication or external write occurs without the configured permission and, where required, explicit human approval.
- Duplicate events do not create duplicate leads, messages or bookings.
- Missing, stale or conflicting knowledge causes a safe clarification or human handoff.
- Provider timeout, outage, malformed response and cancellation are visible and recoverable.
- The employee can be disabled without affecting Professor or unrelated departments.
- A synthetic end-to-end demonstration records source, actor, tenant, request ID, decisions, approvals and outcome.
- Mobile Safari usability, keyboard accessibility and clear failure states are tested.

Exit gate: one repeatable synthetic end-to-end demonstration and an operator dashboard, with no production writes, live customer messaging, payment activation or unapproved provider connection.

### Phase 3 — Atlas Market Intelligence & Trading (paper-only)

Build a broker-independent market research and simulated-trading department. Support all major market categories over staged, provider-verified integrations: equities and ETFs, FX, cryptoassets, indices and commodities where lawful market-data access and a suitable instrument/data provider exist. "All markets" is the long-term coverage objective, not a claim that every broker offers every instrument or that every feed is available in every jurisdiction.

1. Establish the department boundary separately from business Finance, Atlas subscription billing and personal financial records.
2. Build provider-neutral instrument, quote, OHLCV candle, corporate-action, trading-session, currency, spread and market-data provenance contracts.
3. Implement market-data adapters behind explicit provider configuration and documented data-licensing checks. Assess Trading 212 first for eligible read-only account/portfolio access and its supported demo capabilities; assess other brokers/data vendors independently. Never assume API feature parity.
4. Build a charting and market-monitoring workspace with configurable watchlists, timeframes, candles, volume, indicators, alerts and clear stale/delayed-data labels.
5. Build a strategy research lab with versioned strategies, deterministic backtests, realistic fees/spread/slippage assumptions, no look-ahead leakage, train/test separation, walk-forward evaluation and benchmark comparisons.
6. Build an internal paper-trading engine that simulates orders, fills, positions, cash, fees, P&L and risk. Use real market data only where licensing and provider terms allow; otherwise label fixtures/synthetic feeds clearly.
7. Add risk controls: per-strategy and portfolio exposure limits, maximum simulated loss/drawdown, concentration limits, order-size caps, market/session checks, duplicate-order protection, cancellation and an emergency stop.
8. Add Professor explanations with source timestamps, assumptions, uncertainty, strategy version, signal inputs and risk metrics. Signals are hypotheses, not promises or personalised investment advice.
9. Add an audit and performance dashboard covering signals, rejected trades, simulated orders, fills, open positions, drawdown, fees and strategy versions.
10. Keep live broker order execution absent or unreachable in this phase. Any future live-trading proposal requires a separate legal/regulatory review, broker-specific design, explicit owner approval and a new security review.

Exit gate: reproducible paper-trading demonstration across representative asset classes, robust backtest and risk tests, clear market-data provenance, and automated proof that no live order can be submitted.

### Phase 4 — Finance and Hospitality foundations
Finance:
1. Approve the initial chart-of-accounts model and record types.
2. Implement organisation-owned income/expense and invoice/bill records with immutable audit history.
3. Add budgets, cash-flow views and management reports.
4. Validate totals, currency handling, period boundaries, duplicate prevention and export permissions.

Hospitality:
1. Define the Hospitality Hub manifest and role/scope matrix.
2. Verify Quick Chef's real supported integration surface.
3. Start with read-only status/profile/booking summaries using synthetic contract tests.
4. Add a controlled non-production connection only after the API and identity boundaries are verified.

Exit gate: finance records reconcile in tests; Hospitality can fail independently; no live Quick Chef data or payments are changed.

### Phase 5 — HR and Legal foundations
Build restricted records, role matrices, retention rules, approval steps and audit trails. Keep payroll execution and legal filing/signature actions out of scope until separately approved.

### Phase 6 — Velvet foundations
Complete the 18+ safety, age-assurance, consent, moderation, privacy and separate commercial architecture before any public-facing launch or sensitive data collection.

### Phase 7 — Integration and commercial readiness
Add additional arms one at a time, complete security/privacy review, operational support, backup/restore, accessibility, load and mobile testing, then conduct a controlled pilot. Commercial launch is a separate human approval gate.

## 7. Acceptance criteria for the foundation

- A user can see only departments enabled for their organisation and authorised by their membership.
- A department cannot read another organisation's records by changing an ID or request parameter.
- A module cannot perform an action without its exact required scope.
- Professor can delegate a task without receiving department credentials or bypassing department policy.
- An unavailable department does not break the core shell.
- Every sensitive operation produces a minimal, useful audit event.
- Department responses are schema-validated and treated as untrusted content.
- Each module can be disabled without deleting data or disabling unrelated modules.
- Finance, billing, personal trading and Velvet data remain separate.
- No production data, live payment settings, external credentials or deployment configuration are changed by the foundation work.

## 8. Explicit non-goals for this foundation

- No merge or deployment.
- No live login/provider activation.
- No payment-provider selection, checkout, webhook or live charging.
- No bank connection, trade placement, payroll execution or tax filing.
- No production Quick Chef database access or migration.
- No automatic legal filing or execution.
- No Velvet public launch or collection of adult-content data.
- No autonomous self-modification or permission escalation.

## 9. Immediate next engineering task

After this architecture is reviewed, inspect the current application and existing identity/security stack to locate the correct integration point. Then implement the smallest testable department-registry contract on an isolated branch. Do not build department business logic on top of unverified tenant or permission boundaries.
