# AtlasOnePro — Professor Core

AtlasOnePro is the wider platform. The **Professor** is its central reasoning and orchestration component. This repository currently contains an early Python prototype of the Professor's task, evaluation, learning-record and media foundations. It is not yet the complete AtlasOnePro platform.

## Current prototype capabilities

- FastAPI service and public health checks
- Task creation and local, restricted arithmetic execution
- Deterministic success-criteria evaluation
- SQLite persistence for tasks, evaluations, lessons and proposals
- Human-reviewed improvement proposals
- Optional media endpoints with local image fallback
- No live brokerage transactions, automatic social posting or autonomous external actions

## Development principles

- Preserve existing work; do not create duplicate applications.
- Keep paid AI providers disabled unless explicitly approved.
- Keep financial integrations read-only until separately reviewed and approved.
- Require human review before a proposal can pass the approval gate.
- Approval is not permission to deploy; production changes require a separate controlled release process.
- Keep credentials in environment variables, never in source control.

## Setup

Use Python 3.11 or later.

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env

Edit .env and replace the example ATLAS_API_KEY with a long random secret. The app loads .env automatically. Start the local server:

    uvicorn app:app --host 127.0.0.1 --port 8000

On Windows, activate the virtual environment with .venv\\Scripts\\activate.

For a trusted local-only development session, authentication can be disabled with ATLAS_API_REQUIRE_AUTH=false. Do not use that setting on a network-accessible or public deployment. When started with `python app.py`, the server binds to `127.0.0.1` while authentication is disabled and uses `0.0.0.0` only when API-key authentication is enabled. If starting Uvicorn directly, keep the explicit loopback host shown above for local-only use.

## API access

- GET /health — public liveness check
- GET /media/health — public media liveness check
- All task, evaluation, lesson, proposal, dashboard and media-generation routes require the X-API-Key header by default.

Example:

    curl http://127.0.0.1:8000/tasks -H "X-API-Key: YOUR_SECRET"

The API key is a shared-secret development control, not per-user identity, role-based authorization or multi-tenant authentication. The approved_by proposal field is caller-supplied audit metadata, not independently verified identity. Do not expose this prototype as a public multi-user service.

Media output paths are constrained to ATLAS_MEDIA_OUTPUT_DIR. Path traversal and symlink escapes are rejected by the media generator.

## Architecture

See [the Professor orchestration blueprint](docs/professor-orchestration.md) for the verified current boundaries, target octopus/capability model, staged delivery plan and release gates. It is design guidance, not a claim that the future orchestration or integrations are already implemented.

## Professor Source Division interface

Open `/professor/sources` in the running AtlasOnePro instance to use the browser-based source catalogue, import queue and approved-knowledge search. Enter the configured API key in the page; it is held in page memory only and is not persisted in browser storage. The default `manual-paste`, `github-public`, `huggingface-public`, `uk-legislation`, `crossref-public` and `public-web` sources are registered at application startup. The page can fetch bounded GitHub repository metadata, Hugging Face model/dataset metadata, official UK legislation search results and XML text, Crossref scholarly bibliographic records, and individual public HTML/plain-text pages from an exact-host allowlist. Public-web retrieval is restricted to approved HTTPS hosts on port 443, revalidates redirects, rejects non-public DNS destinations, uses an eight-second timeout and a 1 MB cap, and excludes script/style/navigation/form content. Retrieved page text is marked untrusted and remains pending/unverified; it must be treated as data, never as instructions. This is not unrestricted crawling. No private resources, model weights, credentials, publisher full text or write actions are accessed. The interface does not approve documents. Source metadata is restricted to finite JSON, at most 16 KiB and 32 levels deep; credential-like field names are rejected.

## Useful endpoints

- POST /sources/fetch — fetch and stage GitHub, Hugging Face, UK legislation or Crossref research
- POST /sources/fetch-url — fetch one allowlisted public web page and stage it as untrusted
- GET /sources — source catalogue
- GET /sources/documents — bounded review queue
- POST /sources/import — stage a JSON batch for review
- GET /sources/search — approved-only knowledge retrieval
- GET /dashboard
- GET /tasks
- POST /tasks
- POST /tasks/{task_id}/run
- GET /tasks/{task_id}/evaluations
- GET /tasks/{task_id}/attempts
- POST /tasks/recovery/scan
- GET /tasks/recovery-required
- POST /tasks/{task_id}/recovery-decision
- POST /tasks/{task_id}/cancel
- GET /tasks/{task_id}/cancellation
- GET /tasks/{task_id}/retry-schedules
- GET /tasks/retries/due
- POST /tasks/retries/expire
- GET /lessons
- GET /proposals
- POST /proposals/{proposal_id}/review
- POST /media/generate-image
- POST /media/generate-video

## Recovery, cancellation and retry boundaries

Task attempts use durable SQLite leases and fencing tokens. An expired lease is moved to `recovery_required`; it is never automatically replayed. Recovery decisions require an authenticated operator route and explicit safety/reconciliation attestations.

Cancellation requests are durable and tied to one attempt. The worker checks at safe points around the bounded synchronous local executor; it does not kill work mid-operation. If a request arrives after a retry has been scheduled but before its next attempt is claimed, the schedule is cancelled and the task is terminalised. If the lease has expired, cancellation requires operator recovery.

Retry schedules are persisted with due time, deadline, attempt number, capability metadata, idempotency key and policy snapshot. Claims before the due time or after the deadline are blocked. Authenticated due-schedule inspection is read-only; authenticated expiry maintenance terminalises overdue tasks with an evaluation. Inspection responses omit idempotency keys and internal policy/capability snapshots. The current executor does not create retry schedules, there is no unattended retry scheduler, and no automatic retry is enabled.

Execution failures are persisted with a sanitised evaluation. A secondary `execution_failure` lesson may be recorded as unvalidated, with only the exception class and evaluation ID; unvalidated lessons are excluded from retrieval until reviewed. If the evaluation transaction fails, the API returns `outcome_unconfirmed` and does not claim a durable terminal result.

## Proposal safety boundary

Proposal approval only makes a proposal eligible for controlled change review. It does not run code, alter production or deploy anything. The proposal action that marks work as tested is intentionally disabled: this repository does not yet have a trustworthy, isolated proposal-test runner. A proposal must not be marked tested without actual test evidence.

The current temporary-directory test runner is not an operating-system security sandbox and must not be used to execute untrusted proposal code. The local executor only accepts basic arithmetic expressions.

## Tests

    python -m pytest -q

## Future production requirements

Before public or commercial deployment, add a proper identity provider, role-based authorization, tenant isolation, audit logging, secrets management, threat modelling, dependency scanning and independent security testing. This prototype is not yet SOC 2, ISO 27001, Cyber Essentials or UK GDPR compliance evidence.

Do not connect it directly to live financial accounts or enable external actions until those integrations have been separately designed, permissioned and reviewed.
