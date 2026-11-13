# AtlasOnePro — Professor Core

AtlasOnePro is the wider platform. The **Professor** is its central reasoning and orchestration component. This repository currently contains an early Python prototype of the Professor's task, evaluation, learning-record and media foundations. It is not yet the complete AtlasOnePro platform.

## Current prototype capabilities

- FastAPI service and health endpoint
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
- Require human approval for production-impacting changes.
- Keep credentials in environment variables, never in source control.

## Setup

Use Python 3.11 or later.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app:app --host 0.0.0.0 --port 8000
```

On Windows, activate the virtual environment with `.venv\\Scripts\\activate`.

## Useful endpoints

- `GET /health`
- `GET /dashboard`
- `GET /tasks`
- `POST /tasks`
- `POST /tasks/{task_id}/run`
- `GET /lessons`
- `GET /proposals`
- `POST /media/generate-image`
- `POST /media/generate-video`

## Tests

```bash
python -m pytest -q
```

## Security notes

Set `ATLAS_MEDIA_REQUIRE_AUTH=true` and a strong `ATLAS_API_KEY` before exposing media-generation endpoints outside a trusted development environment. Review all API routes and deployment settings before public release.

The current local executor only accepts basic arithmetic expressions. Do not treat this prototype as a general-purpose autonomous agent or connect it directly to live financial accounts.
