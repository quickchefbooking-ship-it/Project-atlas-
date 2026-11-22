# Professor Local Runtime Bring-up Guide

**Purpose:** A free, loopback-only route to prove the core app starts and its health/readiness diagnostics respond. This is a test guide, not a deployment approval or production runbook.

## Safety
- Run on your own trusted computer only, bound to `127.0.0.1`.
- Keep `ATLAS_CAPABILITY_EXECUTION_ENABLED=false`.
- Keep paid AI off and `ATLAS_LLM_PROVIDER=off` for the first smoke test.
- Do not use real personal, financial, child, legal, or customer data.
- Do not expose this prototype to the internet, LAN, reverse proxy, or public tunnel.
- Do not commit `.env`, API keys, tokens, database files, or generated outputs.

## 1. Obtain and inspect the test source (currently approval-blocked)
Do **not** assume PR #82 is the current or approved source. As of 22 November 2026:

- PR #85 atomic conversation/audit draft head `f7cc1fa9a0e9b2fbceac6055d6ffe02efc5ff51d` passed merge-ref CI run [45054846603](https://github.com/quickchefbooking-ship-it/Project-atlas-/actions/runs/45054846603) with 1187 tests, but it is stacked on PR #84 head `c58f5856ed5a557c4deaa02333f5ec4e89825ecb`.
- PR #84 diverges from PR #48 prompt-budget head: 143 commits ahead / 3 behind, with four differing overlapping files. PR #85 is not a clean release source.
- PR #63 hosted OIDC startup composition head `167f9986124013608544a62cf27bbfc8de991095` passed run [44167021419](https://github.com/quickchefbooking-ship-it/Project-atlas-/actions/runs/44167021419) (1101 tests) but is a separate diverged draft.
- PR #83 readiness-test head `d101a6303422e2b73028847c5d6bbac97cf95fe3` passed run [45049237138](https://github.com/quickchefbooking-ship-it/Project-atlas-/actions/runs/45049237138) (1181 tests) but also differs from PR #85.

A maintainer must select/reconcile a clean branch before this smoke guide is executed. Check out that exact SHA, inspect it, and never assume it is production source. No merge or deployment is authorized by this guide.
**Dependency baseline blocker:** default `main` currently has `requirements.txt` containing application Python source rather than a pip requirements list. PR #1 repairs/pins the baseline (9 dependencies; exact CI run 43489002177 passed 237 tests) but remains draft/unmerged. PR #85 branch has 12 pinned dependencies and CI 1189 passed, but its stack is diverged from PR #1 (855 ahead/1 behind). Do not run or install from `main` or assume PR #1 is integrated; maintainer must reconcile dependencies and select a clean source SHA.


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
