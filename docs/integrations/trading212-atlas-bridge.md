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
