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

For a trusted local-only development session, authentication can be disabled with ATLAS_API_REQUIRE_AUTH=false. Do not use that setting on a network-accessible or public deployment.

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

## Useful endpoints

- GET /dashboard
- GET /tasks
- POST /tasks
- POST /tasks/{task_id}/run
- GET /tasks/{task_id}/evaluations
- GET /lessons
- GET /proposals
- POST /proposals/{proposal_id}/review
- POST /media/generate-image
- POST /media/generate-video

## Proposal safety boundary

Proposal approval only makes a proposal eligible for controlled change review. It does not run code, alter production or deploy anything. The proposal action that marks work as tested is intentionally disabled: this repository does not yet have a trustworthy, isolated proposal-test runner. A proposal must not be marked tested without actual test evidence.

The current temporary-directory test runner is not an operating-system security sandbox and must not be used to execute untrusted proposal code. The local executor only accepts basic arithmetic expressions.

## Tests

    python -m pytest -q

## Future production requirements

Before public or commercial deployment, add a proper identity provider, role-based authorization, tenant isolation, audit logging, secrets management, threat modelling, dependency scanning and independent security testing. This prototype is not yet SOC 2, ISO 27001, Cyber Essentials or UK GDPR compliance evidence.

Do not connect it directly to live financial accounts or enable external actions until those integrations have been separately designed, permissioned and reviewed.
