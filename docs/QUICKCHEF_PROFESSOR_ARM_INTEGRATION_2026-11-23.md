# QuickChef as a Professor Arm — Integration Plan (2026-11-23)

## Direction
QuickChef remains its own product, application, database, identity/security boundary, and operational domain. THE PROFESSOR becomes the orchestration/reasoning layer and uses QuickChef through a versioned arm/connector contract. Avoid merging QuickChef source into the Professor core.

## Proposed capability surface
- `quickchef.health`: read-only connector health and version.
- `quickchef.summary`: high-level counts/status, scoped by authorized tenant.
- `quickchef.chefs.search`: search chef directory with explicit filters and return references.
- `quickchef.chef.profile`: fetch one authorised profile by ID.
- `quickchef.verification.status`: read verification/completion state.
- `quickchef.bookings.search`: query bookings by date/status/region.
- `quickchef.booking.details`: retrieve a specific authorised booking.
- `quickchef.analytics`: bounded operational summaries.
- Later, separately gated write capabilities: booking create/update/cancel, notifications, moderation, payouts, etc. These must not be enabled in the first connector phase.

## Adapter contract
- Versioned request/response schema; connector identity; tenant/user identity; permission scopes; request correlation ID; timeout and rate limit; structured errors; provenance; audit metadata.
- Read-only first; deny by default if identity/scope cannot be verified.
- No credentials in prompts, memory, logs, or returned user-visible results.
- Professor memory stores only minimised summaries/references, not a duplicate QuickChef database or sensitive profile payload.
- Every retrieved item includes source system, record ID/reference, retrieved-at timestamp, and access-scope metadata.
- Avoid broad data sync. Query on demand and cache only safe, permitted, time-bounded results.

## Integration stages
1. Register QuickChef as an arm with metadata, health and declared capabilities; no secrets or data access.
2. Build read-only adapter in a separate module; use mocked contract tests.
3. Obtain an authorised non-production API contract/credential and test with least privilege; no live production credentials until explicitly approved.
4. Implement retrieval and query intents; tests for tenant isolation, scope denial, injection, timeout, pagination, and data minimisation.
5. Add Professor-side summaries, explainable answers and citation/reference links back to QuickChef.
6. Evaluate a human-approved workflow for selected writes, with preview, idempotency, confirmation, and audit. Keep disabled until explicit approval.
7. Consider unified UI/SSO only after connector boundaries and security review are proven.

## Acceptance criteria for read-only pilot
- A health call and one bounded read query work against a test environment.
- User/tenant scope is enforced at QuickChef and connector layers.
- Results are attributable and freshness is disclosed.
- No write endpoint is called; test suite proves write capabilities are unavailable/denied.
- Secrets are handled outside the reasoning/memory context.
- Failures are graceful and do not hallucinate data.
- Connector can be disabled independently without affecting Professor core.

## Effort assessment
Architecture and registration: low effort. Read-only adapter and test contract: moderate, dependent on QuickChef's actual API/auth surface. Secure production integration and unified identity: moderate-to-high, mainly due to identity, tenancy, privacy, audit and deployment requirements. The current repo has capability-registry foundations, but this plan does not claim a working QuickChef connector exists.
