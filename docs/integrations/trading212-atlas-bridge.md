# Trading 212 → AtlasOnePro Finance bridge

## Status

**Contract milestone only.** The Atlas-side normalized portfolio contract and service-principal authorization contract are now defined. They do not connect to TRADING, Trading 212, Clerk, an identity provider, or any network endpoint. No credentials are stored in AtlasOnePro.

## Existing TRADING application findings

The existing TRADING project reports these owner-protected routes:

- `GET /api/trading212/status`: local configuration and owner-binding status only; it does not contact the broker.
- `GET /api/trading212/account/summary`
- `GET /api/trading212/cash`
- `GET /api/trading212/positions`
- `GET /api/trading212/instruments`
- `GET /api/trading212/exchanges`
- `GET /api/trading212/history/orders`
- `GET /api/trading212/history/transactions`
- `GET /api/trading212/history/dividends`

The broker-read routes require a valid TRADING Clerk identity matching the configured owner. These routes are not a cross-application authorization contract. AtlasOnePro must not forward Clerk cookies, reuse broker credentials, or assume that a shared user or domain grants access.

The TRADING status response can establish that the signed-in owner matches the configured owner and that Demo credentials are present. A `configured_not_tested` result is not broker authentication evidence.

## Atlas-side normalized portfolio contract

`atlas_engine.finance_integration_contract` defines verified provenance, normalized finite Decimal values, immutable positions, a read-only snapshot protocol and a freshness gate. A snapshot is rejected unless both owner verification and broker authentication are explicitly true. It has no order, trade, transfer or withdrawal method.

## Atlas-side service-principal authorization contract

`atlas_engine.finance_service_auth` defines a provider-neutral, fail-closed claim contract for a future trusted verifier:

- exact configured issuer and API audience;
- allowlisted service subject;
- short-lived token timestamps with bounded clock skew;
- unique token identifier (`jti`);
- the single allowed capability `finance:portfolio:read`;
- Demo environment only.

Tenant and account identifiers are intentionally absent from caller-supplied claims. Atlas must resolve tenant membership and account ownership from server-side records after authenticating the service principal. No caller-supplied tenant/account value may select a portfolio.

**Important limitation:** the module validates claims only after a trusted verifier has authenticated them. It does not verify JWT signatures, fetch JWKS, validate a live key rotation, persist or reject replayed `jti` values, establish tenant/account mapping, or provide an HTTP middleware/endpoint. Those remain mandatory before any connection is enabled.

## Read-only TRADING API contract audit

A read-only inspection of the existing TRADING checkout compared `lib/api-spec/openapi.yaml` with the route, service and application implementations. No files were changed and no broker endpoint was invoked.

The audit found these concrete OpenAPI corrections needed before a bridge client is generated:

- **Authentication:** operations do not declare machine-readable Clerk-session security. The existing Clerk owner check is enforced in the router; it is not the same as an MCP integration token or a future Atlas service token. Keep the owner check and document its 401/403 behavior and the owner-not-configured variants.
- **Status schema:** actual status payloads include `statusLabel` and `cashRead`, but the closed `Trading212ConnectionStatus` schema omits them.
- **Cash provenance:** the cash response includes `dataOrigin`; the closed generic read-result schema omits it.
- **Error variants:** authentication, owner mismatch, same-origin rejection and unexpected server errors omit fields required by the current `Trading212Error` schema. Its enum omits `authentication_required` and `same_origin_required`.
- **Timeout and validation statuses:** upstream/local timeouts return 504, not the documented 408. Several GET operations can return 400 for invalid environment/query input; unexpected errors can return 500.
- **History pagination:** each call returns one page. `nextPagePath` cannot be combined with `limit`, `ticker` or `time`. The documented order-history `time` parameter is not accepted by the implementation; only transaction history accepts it.
- **Payload typing:** account summary/cash are top-level objects, positions are top-level arrays, and history is an object containing `items` and `nextPagePath`. The shared schema is too broad and its item constraints do not match the runtime validator. Do not invent guaranteed provider position fields.
- **Response headers:** the router sends `Cache-Control: no-store, private`, `Pragma: no-cache` and `X-Trading212-Write-Capability: disabled`; rate-limit and retry headers may also be present.
- **Connection test:** the OpenAPI description permits Live, while the implemented test-connection handler is Demo-only and same-origin protected.

The minimal backwards-compatible correction is to preserve existing paths, operation IDs and runtime payloads; add route-specific top-level response schemas and typed optional provenance; model the actual error variants with `oneOf`; document actual HTTP codes and pagination constraints; and add a distinct Clerk-session security scheme. Do not describe that scheme as Atlas service authentication.

## Replay protection boundary

`atlas_engine.finance_service_auth` now defines a `FinanceReplayStore` protocol and a fail-closed guard that atomically consumes a verified token ID before a Finance read. This is an interface and enforcement seam only. The test double is process-local and is not suitable for production. A durable, shared atomic implementation (for example, a transactional database uniqueness constraint or an equivalent atomic cache operation), expiry cleanup and operational monitoring remain required. If replay storage is unavailable, the read must fail closed.

## Next integration stages

1. Reconcile TRADING's OpenAPI schema with actual response fields and add machine-readable authentication requirements.
2. Select and implement an audited service identity provider/verifier; validate signature, algorithm, issuer, audience, expiry and not-before claims.
3. Add durable replay protection for token IDs and server-side service-to-tenant/account mapping.
4. Add a TRADING-side adapter endpoint that returns only normalized, non-secret portfolio data to an authenticated Atlas service principal after owner and account checks.
5. Add the Atlas adapter, secret storage and tenant-scoped account mapping.
6. Run a Demo-only authenticated read test, record provenance and freshness, and display data in Professor Finance.
7. Keep Live account access and every financial write operation disabled unless separately approved and designed.

## Release gates

- No broker credentials in browser code, logs, source control, or Atlas request payloads.
- No direct browser-to-broker requests.
- No bypass of the TRADING Clerk owner check.
- No trust in client-supplied account owner, tenant or account IDs.
- No claim that local configuration status proves broker connectivity.
- No order or transfer methods in the read-only Finance capability.
- No merge, deployment, or Live access as part of this contract milestone.
