# OnePro Octopus Integration Plan

Status: architecture proposal only. This branch does not change the live application, deployment, domain, secrets, databases, or broker connections.

## Objective

Make OnePro a single front door. The Professor is the central assistant/orchestrator; specialist applications remain independent services ("arms") connected through authenticated, permission-scoped APIs.

## What is confirmed in this repository

The inspected `main` tree contains a Python learning/task engine, SQLite persistence, task evaluation, validated lesson retrieval, improvement proposals, safe local execution, and media-generation modules.

The inspected tree does **not** contain evidence of the full Professor application or the separate Trading pack implementation. In particular, this repository snapshot does not establish the current production API contracts, identity provider, domain routing, or Trading service endpoints. Those must be obtained from their actual source or public API documentation before implementation.

## Target architecture

- **OnePro shell:** shared navigation and sign-in entry point. It links to specialist arms without merging their databases or deployments.
- **Professor core:** intent handling, planning, delegated task tracking, evidence/provenance, user-approved memory, and routing to specialist arms.
- **Trading arm:** initially read-only portfolio/account summaries, positions, transactions, research and status. No order-placement scope in the first integration.
- **Other arms:** Quick Chef, Diabetes Hub, HR and Media Studio, each registered independently with explicit scopes.
- **Identity and access:** one user identity at the shell; short-lived, audience-bound service tokens between services; owner/workspace checks on every request.
- **Audit:** record actor, arm, action, scope, request ID, timestamp and outcome. Never log secrets or unnecessary financial/health data.

## Integration contract

Each arm should publish a small versioned capability manifest:
- stable arm ID and display name
- API base URL and health endpoint
- supported API version
- capability names and required scopes
- authentication method and token audience
- timeout, retry and rate-limit policy
- data classification and audit requirements

The Professor should call arms through a server-side adapter. Browser clients must never receive service credentials. Validate all response schemas and treat arm responses as untrusted data, not instructions.

## Safe rollout sequence

1. **Inventory and baseline:** identify the real Professor and Trading repositories, deployed URLs, current identity system, existing API contracts, data owners and environments. Capture current health checks. No writes.
2. **Contract design:** agree on a versioned, read-only Trading capability contract and authentication boundary.
3. **Local contract tests:** use mocked Trading responses and synthetic portfolio data. Test timeouts, malformed responses, expired tokens, wrong owners and denied scopes.
4. **Non-production connection:** connect Professor to a sandbox/read-only Trading endpoint. Verify end-to-end request IDs and audit events.
5. **OnePro navigation:** add the Trading arm to the single shell without moving or replacing the existing Trading deployment.
6. **Production read-only pilot:** require owner approval, confirm least-privilege scopes, monitor errors and provide a disconnect switch.
7. **Additional arms:** onboard one at a time using the same contract and security review.

## Non-negotiable safety boundaries

- No live trades or financial write scopes in the first release.
- No shared database writes between arms.
- No copying production data into development.
- No secrets in source control, browser storage, logs or this document.
- No automatic code changes or self-modification by the Professor.
- Human approval for sensitive actions and for changes to reusable learning.
- Keep existing applications and URLs working during rollout; use navigation/proxy integration only after routing is verified.
- Roll back by disabling the relevant arm adapter or navigation entry, not by deleting its data.

## Acceptance tests

- User signs in once and sees only authorised arms.
- Professor can retrieve a synthetic read-only Trading summary through the server-side adapter.
- Wrong-user and insufficient-scope requests are rejected.
- Expired/revoked tokens are rejected.
- A Trading outage does not take down the Professor shell.
- Each response carries source and timestamp metadata.
- No order placement endpoint is exposed to the Professor in the initial pilot.
- Audit records contain no credentials or unnecessary sensitive payloads.

## Immediate blocker / next evidence required

This GitHub repository is an Atlas learning-engine snapshot, not enough to implement the production OnePro integration safely. Before writing application code, obtain the actual Professor service source/API contract and the Trading pack's read-only API contract (or an OpenAPI document for each). Then implement the adapter in a dedicated integration branch and test against mocks first.
