# Synthetic market watchlist API adapter

This draft adds a standalone FastAPI router at `GET /market/watchlist`.

## Contract

- Uses the existing version-1 JSON serializer and deterministic synthetic snapshot.
- Identifies the response as a read-only demo fixture and carries the notice that it is not live market observations.
- Preserves instrument identity, source provenance, quality labels and precision-safe decimal strings.
- Makes no network, provider, broker, account, persistence or order calls.

## Integration boundary

The router is not yet included in the main application. It is tested through a small FastAPI harness so the route contract can be reviewed independently of the concurrent `app.py` authentication/startup changes in PRs #55, #63 and #64. Application wiring, authentication/visibility policy and deployment verification are a separate reviewed step.

## Verification

The focused tests exercise the HTTP response, deterministic fixture content, explicit synthetic labels, JSON safety and method handling. GitHub Actions must validate the exact PR head before this slice is considered verified.
