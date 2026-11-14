# Trading 212 → AtlasOnePro Finance bridge

## Status

**Contract milestone only.** This document and the normalized Python contract define the Atlas-side boundary. They do not connect to TRADING, Trading 212, Clerk, or any network endpoint. No credentials are stored in AtlasOnePro.

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

## Atlas-side normalized contract

`atlas_engine.finance_integration_contract` defines:

- provenance: source, Demo/Live environment, non-secret account reference, owner verification, broker authentication, fetch timestamp and request ID;
- normalized cash and total values using finite Decimal amounts;
- typed position records and immutable position collections;
- a read-only source protocol with one snapshot method;
- a freshness gate that rejects stale or future-dated snapshots.

A snapshot is rejected unless both owner verification and broker authentication are explicitly true. The contract deliberately has no order, trade, transfer or withdrawal method.

## Next integration stages

1. Reconcile TRADING's OpenAPI schema with its actual response fields and add explicit machine-readable authentication requirements.
2. Define a dedicated Atlas service-to-service authorization mechanism, narrowly scoped to read-only portfolio data. Do not use a shared API key as a production cross-app identity mechanism.
3. Add a TRADING-side adapter endpoint that returns only normalized, non-secret portfolio data to an authenticated Atlas service principal after owner and account checks.
4. Add the Atlas adapter implementation, secret storage and tenant-bound account mapping only after the authorization contract is reviewed.
5. Run a Demo-only authenticated read test, record provenance and freshness, and display the data in Professor Finance.
6. Keep Live account access and every financial write operation disabled unless separately approved and designed.

## Release gates

- No broker credentials in browser code, logs, source control, or Atlas request payloads.
- No direct browser-to-broker requests.
- No bypass of the TRADING Clerk owner check.
- No trust in client-supplied account owner or tenant IDs.
- No claim that a local configuration-status response proves broker connectivity.
- No order or transfer methods in the read-only Finance capability.
- No merge, deployment, or Live access as part of this contract milestone.
