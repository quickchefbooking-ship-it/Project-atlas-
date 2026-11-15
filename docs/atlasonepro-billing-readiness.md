# AtlasOnePro — Billing and live-payment readiness

**Status:** design-only readiness specification. No payment provider is selected or configured, no prices are approved, and no payment or entitlement route is enabled.

## Purpose and scope

AtlasOnePro may be sold to organisations or individuals as a subscription service. Billing is a commercial control plane around the Professor; it is not part of the reasoning engine and must never be required for local development, core reasoning tests, or safe offline operation.

This specification applies only to AtlasOnePro. It does not reuse Quick Chef payment accounts, customer records, products, prices, webhook endpoints, credentials, databases, or deployment settings.

The Professor's brain remains the primary build. Billing is a separately gated workstream and must not divert or weaken the identity, tenant, memory, reasoning, and capability-safety work.

## Non-negotiable isolation

- Use a dedicated AtlasOnePro payment-provider account or an explicitly isolated provider project. Never share Quick Chef's account or credentials.
- Keep test and live environments separate at every layer: API credentials, webhook signing secrets, products/prices, customer identifiers, event stores, logs, and deployment configuration.
- Reject a test credential in live mode and a live credential in test mode. Missing, mixed, malformed, or unknown environment configuration must fail closed.
- Never copy customer IDs, subscription IDs, payment-method references, event IDs, or webhook secrets between Quick Chef and AtlasOnePro.
- Do not store or log card numbers, CVCs, raw payment credentials, or full payment-method payloads. Prefer provider-hosted checkout and customer portal flows so card data stays with the provider.
- No live charging, production webhook, public billing route, or paid service is enabled by this design.

## Proposed billing boundary

Keep billing outside the Professor reasoning and capability-execution boundary.

1. A billing adapter communicates with the selected provider using server-side credentials only.
2. A checkout-session service creates a provider-hosted checkout session for an approved AtlasOnePro product and price.
3. A webhook receiver verifies the provider signature against the environment-specific secret before accepting an event.
4. An append-only event ledger records verified provider event identifiers and processing outcomes. Enforce unique event IDs and idempotent handling.
5. A subscription projection stores the minimum required provider customer/subscription references, product/price identifiers, status, period boundaries, cancellation state, and tenant ownership.
6. An entitlement service derives access from verified subscription state and server-owned product policy. The browser, model, user-supplied metadata, and payment redirect must never grant entitlements.
7. An audit trail records checkout initiation, verified event processing, entitlement changes, administrative overrides, and reconciliation outcomes without recording payment secrets or card data.

The Professor may read a narrowly scoped entitlement decision when a paid feature is requested. It must not be able to change subscription state, create refunds, alter prices, or grant itself paid access.

## Event and entitlement rules

- Verify webhook signatures before parsing an event as trusted.
- Persist the event receipt before applying a state transition; process each provider event idempotently.
- Handle duplicate, delayed, replayed, and out-of-order events safely. Reconcile current subscription state with the provider where event order is ambiguous.
- Treat checkout completion as a signal to verify the subscription, not as sufficient proof by itself.
- Define explicit policy for active, trialing, past-due, unpaid, paused, cancelled, expired, and refunded/disputed states before enabling entitlements.
- Any grace period, access downgrade, refund, dispute, or cancellation policy requires an explicit product-owner decision and tests. Do not invent a grace period.
- Administrative overrides must require verified human identity, least-privilege scope, reason, expiry where applicable, and an immutable audit event.
- Tenant ownership must be resolved server-side and enforced on every billing read/write. Cross-tenant identifiers must not disclose customer or subscription data.

## Required test-only acceptance journey

Before considering live readiness, implement and prove the following entirely in the dedicated AtlasOnePro test environment:

1. Create a test checkout session for a product/price explicitly approved for AtlasOnePro.
2. Complete provider-hosted test checkout with a test payment method.
3. Receive a signed test webhook and verify signature rejection for invalid, missing, or wrong-environment secrets.
4. Process the same event more than once and prove there is one effective state transition.
5. Exercise delayed and out-of-order events and prove reconciliation cannot grant stale access.
6. Verify entitlement grants and revocations for every approved subscription state and policy.
7. Verify cancellation, failed payment, refund/dispute, and customer-portal return paths as applicable to the selected provider.
8. Prove one tenant cannot inspect or alter another tenant's billing records or entitlements.
9. Prove diagnostics, API responses, logs, and error paths do not disclose credentials or payment data.
10. Run the complete CI suite and record the exact commit, workflow run, test counts, warnings, and any skipped checks.

Tests must use synthetic accounts and test-mode payment methods only. No real card data or live customer records.

## Automated live-readiness preflight

A future preflight must report pass/fail/blocked for each item without printing secret values:

- Provider and account identity are the dedicated AtlasOnePro configuration.
- Environment is explicitly set to test or live and matches every credential and webhook secret.
- Required secrets are present, non-empty, correctly scoped, and never echoed.
- Approved product and price identifiers exist in the matching environment.
- Webhook endpoint is registered for the correct environment and required event types.
- Signature verification, replay handling, idempotency, event persistence, and reconciliation tests pass.
- Subscription-to-tenant ownership and entitlement policy tests pass.
- Cancellation, failed-payment, refund/dispute, and portal flows are tested.
- Monitoring, alerting, audit retention, support ownership, backup/restore, incident response, and rollback are documented.
- Privacy notice, terms, cancellation/refund wording, tax/accounting responsibilities, and applicable UK consumer/business obligations have been reviewed by the responsible owner.
- Independent security review has no unresolved critical/high findings relevant to billing.

A missing item blocks live readiness. A green preflight is evidence for a human release decision, not permission to switch to live mode automatically.

## Staged implementation plan

**B0 — Product decisions (blocked pending owner decisions):** choose provider, billing model, customer type, approved products/prices/currency, tax treatment, cancellation/refund policy, and entitlement rules. Do not infer prices or commercial terms.

**B1 — Test-only adapter:** add provider-neutral interfaces and a dedicated test-mode adapter after provider selection. Keep it isolated from Professor reasoning and from all Quick Chef resources.

**B2 — Webhook and ledger:** implement signature verification, idempotent event receipts, state projection, tenant checks, and audit events with focused negative tests.

**B3 — Entitlements and customer self-service:** implement server-derived access, cancellation and portal paths, and admin controls only after verified identity and tenant authorization are in place.

**B4 — Readiness evidence:** run the complete test journey, automated preflight, security review, operational rehearsal, and owner review. Keep live mode disabled.

**B5 — Live release decision:** only after all gates pass, obtain separate explicit approval to configure live credentials, register the live webhook, and enable live charging. This document does not grant that approval.

## Current blockers and next safe action

- No AtlasOnePro billing provider or account has been selected/configured.
- No AtlasOnePro product catalogue, prices, currency, billing cadence, or entitlement policy has been approved.
- Verified identity and tenant isolation remain incomplete in the Professor security roadmap.
- No billing code, checkout route, webhook, secret, production database, or payment configuration is created by this document.

**Next safe action:** finish the existing Professor identity/tenant and reasoning acceptance work. In parallel, obtain explicit product-owner decisions for B0. Only then implement a test-only billing adapter on a separate branch. Do not merge or deploy without separate approval.
