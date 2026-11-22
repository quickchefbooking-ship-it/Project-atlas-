# Professor Local Runtime Bring-up Guide

**Purpose:** A free, loopback-only route to prove the core app starts and its health/readiness diagnostics respond. This is a test guide, not a deployment approval or production runbook.

## Safety
- Run on your own trusted computer only, bound to `127.0.0.1`.
- Keep `ATLAS_CAPABILITY_EXECUTION_ENABLED=false`.
- Keep paid AI off and `ATLAS_LLM_PROVIDER=off` for the first smoke test.
- Do not use real personal, financial, child, legal, or customer data.
- Do not expose this prototype to the internet, LAN, reverse proxy, or public tunnel.
- Do not commit `.env`, API keys, tokens, database files, or generated outputs.

## 1. Obtain and inspect the approved branch
Use the approved PR #82 integration branch/merge-ref only after the maintainer chooses the test source. Check the commit SHA before running. Never assume the branch is the production source.

## 2. Install locally (Python 3.11+)
```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Configure a safe local-only environment
Create a local `.env` from `.env.example` and use these settings for the first smoke test:
```dotenv
ATLAS_DB_PATH=./local-smoke.db
ATLAS_API_REQUIRE_AUTH=false
ATLAS_CAPABILITY_EXECUTION_ENABLED=false
ATLAS_ENABLE_PAID_AI=false
ATLAS_LLM_PROVIDER=off
ATLAS_MEDIA_OUTPUT_DIR=./local-smoke-output
ATLAS_MEDIA_TMP_DIR=./local-smoke-tmp
```
This is only acceptable while the server remains on loopback. Do not use these settings for a network-facing deployment.

## 4. Start the server (loopback only)
```bash
uvicorn app:app --host 127.0.0.1 --port 8000
```
Do not change the host to `0.0.0.0` for this smoke test.

## 5. Verify liveness and configuration (new terminal)
```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/media/health
curl -fsS http://127.0.0.1:8000/build-info
curl -fsS http://127.0.0.1:8000/launch/readiness
curl -fsS http://127.0.0.1:8000/identity/login-readiness
```
Record the exact JSON output and server revision. A health response is liveness only. Readiness may correctly report `not_ready` because identity, hosted login, tenant storage, and live provider checks are not configured.

## 6. Basic UI smoke
Open these on the same computer:
- `http://127.0.0.1:8000/professor/chat` (chat UI)
- `http://127.0.0.1:8000/professor/learning` (learning observability UI)

Confirm pages render, no browser console errors, and no capability execution is triggered. With provider off, a real reasoning reply is not expected.

## 7. Stop and clean up
Stop Uvicorn with Ctrl+C. Review local smoke artifacts and remove the smoke database/output only if they are not needed for evidence. Keep secrets and databases out of Git.

## Required evidence before P5 can move to DONE
- Test source commit SHA recorded.
- Python/dependency install success.
- Server startup log (redacted).
- Health/media-health/build-info responses.
- Launch and login readiness responses.
- Chat and learning UI render checks.
- Any real local-provider conversation: provider/model and response recorded without secrets.
- iPhone Safari check if the test host is reachable securely; do not expose an unauthenticated prototype for convenience.
- All blockers and failures documented.

**Status:** Prepared only. No local runtime has been started from this document by the assistant; P5 remains blocked until the user/authorized test environment executes and evidence is captured.
