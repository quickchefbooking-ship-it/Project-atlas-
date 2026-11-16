# AtlasOnePro — Billing and live-payment readiness

**Status:** staged readiness work only. No provider is selected or configured; no product, price, currency or commercial policy is approved; no checkout, webhook, entitlement or live-payment route is enabled.

## Scope and isolation

Billing is a separate commercial control plane around the Professor. It must not be part of reasoning or capability execution and must not be required for local development or safe offline operation.

This work applies only to AtlasOnePro. It must not reuse Quick Chef payment accounts, credentials, customers, products, prices, webhook endpoints, databases or deployment settings. A dedicated AtlasOnePro provider account/project is required before provider integration.

Use provider-hosted checkout and customer portal pages where possible. AtlasOnePro must not store or log card numbers, CVCs, raw payment credentials or full payment-method payloads. Test and live credentials, webhook secrets, products, customer references, event stores and logs must remain separate. Mixed, missing, malformed or wrong-environment configuration must fail closed.

## Required architecture before test checkout

1. A server-side billing adapter isolated from Professor reasoning and capability handlers.
2. Checkout-session creation restricted to an owner-approved AtlasOnePro product and price.
3. Environment-specific webhook signature verification before an event is trusted.
4. Durable append-only event receipts, unique provider event IDs and idempotent processing.
5. Subscription projection with minimum provider references, state, billing period, cancellation state and tenant ownership.
6. Server-derived entitlements. Browser redirects, model output, user metadata and checkout completion alone never grant access.
7. Audit events for checkout initiation, verified events, entitlement changes, overrides and reconciliation, without secrets or card data.
8. Tenant ownership enforced server-side on every billing read/write; cross-tenant identifiers return non-disclosing responses.

The Professor may read a narrowly scoped entitlement decision. It must never change subscription state, create refunds, alter prices or grant itself paid access.

## Event and entitlement controls

- Persist a verified event receipt before applying a state transition.
- Handle duplicate, delayed, replayed and out-of-order events; reconcile ambiguous state with the provider.
- Define explicit handling for active, trialing, past-due, unpaid, paused, cancelled, expired, refunded and disputed states.
- Do not invent grace periods or access downgrade rules. The owner must approve cancellation, refund, dispute and failed-payment policy.
- Administrative overrides require verified human identity, least-privilege authorization, reason, expiry where appropriate and immutable audit.
- Checkout completion is a signal to verify subscription state, not proof by itself.

## Test-only acceptance journey

Before any live-readiness review, prove all of the following with synthetic accounts and test payment methods only:

1. Create checkout for an explicitly approved AtlasOnePro test product/price.
2. Complete provider-hosted test checkout.
3. Accept a correctly signed test webhook; reject missing, invalid and wrong-environment signatures.
4. Process duplicate events once effectively; safely handle delayed and out-of-order events.
5. Reconcile subscription state without granting stale access.
6. Test every approved entitlement state and grant/revocation rule.
7. Test cancellation, failed payment, refund/dispute and customer-portal paths as applicable.
8. Prove tenant isolation for billing records and entitlements.
9. Prove responses, logs and diagnostics disclose no credentials or payment data.
10. Record exact commit, CI runs, test counts, warnings and skipped checks.

## Live-readiness gates

The deterministic checklist in `atlas_engine/billing_readiness.py` tracks these gate assertions:

- Dedicated AtlasOnePro provider account and verified account ownership.
- Test/live environment and credential isolation.
- Owner-approved products, prices, currency and billing cadence.
- Verified identity and tenant ownership.
- Signed webhook verification and durable idempotent event ledger.
- Subscription reconciliation and server-derived entitlement policy.
- Cancellation, failed-payment, refund/dispute and customer self-service paths.
- Monitoring, audit, support ownership, incident response, backup/restore and rollback rehearsal.
- Privacy notice, terms, cancellation/refund wording, tax/accounting and legal review.
- Independent security review and complete test-mode acceptance journey.

The checklist is deliberately **not an authorization mechanism**. Its inputs are assertions, not independently verified evidence. Even an all-green result is only eligible for separate human review; `live_activation_permitted` always remains false. It does not read secrets, contact a provider, register webhooks, create checkout sessions or enable charging.

## Staged implementation

- **B0 — Owner decisions (currently blocked):** select provider/account; decide customer type, products, prices, currency, billing cadence, tax treatment, cancellation/refund policy and entitlement rules. Do not infer these.
- **B1 — Test-only adapter:** only after B0 and identity/tenant gates, implement a provider-neutral boundary and selected provider's test-mode adapter.
- **B2 — Webhook and ledger:** signature verification, idempotent event receipts, state projection, tenant checks and audit.
- **B3 — Entitlements and self-service:** server-derived access, cancellation/portal paths and verified admin controls.
- **B4 — Evidence:** full test journey, readiness review, security assessment and operational rehearsal. Keep live mode disabled.
- **B5 — Live release decision:** separate explicit approval before live credentials, live webhook registration or charging. No earlier stage grants this approval.

## Current blockers

- No AtlasOnePro provider/account selected or configured.
- No approved product catalogue, prices, currency, cadence or entitlement policy.
- Verified identity, tenant isolation and production-grade audit/operations remain incomplete.
- No payment adapter, checkout route, webhook, payment secret or production payment configuration is implemented.

**Next safe step:** owner decisions for B0, while the Professor identity, tenant and audit foundations continue. Do not activate live payments or reuse Quick Chef's Stripe setup.
