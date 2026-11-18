# AtlasOnePro source reconciliation and safe import plan

**Status:** manifest generator and regression tests prepared on draft PR #65; Replit manifest and source-tree migration outstanding  
**Date:** 18 November 2026  
**Authoritative engineering repository:** `quickchefbooking-ship-it/Project-atlas-`  
**Existing runtime/preview:** Replit app `ATLAS`

## Decision and boundary

The owner has confirmed that this GitHub repository is the authoritative engineering repository. The existing Replit app remains the current runtime/preview environment. The two workspaces are not currently the same source tree and must not be synchronised by copying files over one another.

This document records a safe path to bring the Replit multi-artifact application under the authoritative GitHub repository while preserving both codebases. It does not authorise a deployment, secret change, payment activation, worker activation, or production data migration.

## Read-only inventory verified on 17–18 November 2026

### GitHub repository

- Default branch: `main`
- Main commit: `32471ea720edb5f10ca51aafaf9d45113d4e736c`
- Repository tree: 22 tracked paths
- The separate Professor worker-host-readiness draft PR is #64, head `7aa6e9bf3421840874fe38f80ee7693fd362b72f`.

### Replit workspace

- App: `ATLAS`
- Workspace branch: `main`
- Workspace HEAD: `1cf8d1151c894bb45c1a32f4829d1945fec26d2b`
- Working tree: clean at the last read-only inspection
- Configured remotes: `gitsafe-backup` and `subrepl-shared`
- No GitHub remote or upstream is configured.
- Workspace tree: 846 tracked paths.
- The workspace is a separate multi-artifact app, not a configured checkout of this GitHub repository.

### Tree comparison

- Four paths have the same names in both trees; all four have materially different contents.
- 842 paths are Replit-only.
- 18 paths are GitHub-only.
- The histories have not been reconciled; a shared Git ancestor has not been established.

A previous inventory incorrectly treated `atlas_media/init.py` and `atlas_media/__init__.py` as the same path. They are distinct filenames: Replit tracks `atlas_media/init.py` (149 bytes), while GitHub tracks `atlas_media/__init__.py` (256 bytes). This correction changes the shared-path count from five to four, the Replit-only count from 841 to 842, and the GitHub-only count from 17 to 18. The two files must be preserved independently.

**Manifest limitation:** complete machine-readable per-file path, byte-size, and SHA-256 manifests for both trees have not yet been delivered or attached. The counts and grouped inventory are a corrected summary of the read-only tree inspection, not a substitute for those complete reproducible manifests. This remains an acceptance gate.

Representative Replit-specific areas that must be preserved include:

- `.replit` and the artifact configuration under `artifacts/**/.replit-artifact/`
- `artifacts/project-atlas/**` (web application and web server)
- `artifacts/api-server/**` (API gateway and Python runtime bridge)
- `app/main.py`, `app/transport.py`, and `app/domain.py`
- Replit-specific Brain, Professor, learning, workspace, and Trading 212 modules
- `package.json`, `pnpm-workspace.yaml`, `pyproject.toml`, `uv.lock`, and `scripts/build-api-production.sh`

Representative GitHub-only areas include `app.py`, `atlas_engine/**`, `atlas_media/**`, `requirements.txt`, and the GitHub repository's tests. These must not be treated as replacements for similarly named Replit modules.

## Runtime routing verified from the Replit workspace

- Web artifact: serves `/`; production build uses the `@workspace/project-atlas` package; production serves the built static files.
- API artifact: mounted at `/api` and the OAuth connector path; production build uses `scripts/build-api-production.sh`; the Node gateway starts Uvicorn for `app.main:app`.
- The API gateway and Python API are distinct from the GitHub repository's top-level `app.py` application.

A read-only request to the published Replit `GET /api/build-info` returned JSON 404. The root `/build-info` is served by the web application and returns the HTML app shell. GitHub `main` and the Professor conversation base branch still do not contain the route. However, active draft PR #64 now adds a public `GET /build-info` route to the GitHub FastAPI app, validates a full `ATLAS_BUILD_REVISION`, and returns only the revision or an explicit unknown state. Its exact-head Actions run #2155 passed on `7aa6e9bf3421840874fe38f80ee7693fd362b72f` (1,174 tests, one non-blocking warning). The endpoint is still draft-only, unmerged and undeployed; it does not add the route to the separate Replit API. A duplicate implementation was briefly prepared in PR #67, but its exact-head run failed because the new public route was not added to the security test allowlist. PR #67 has been closed as duplicate, leaving PR #64 as the single active build-provenance implementation.

No automatic `ATLAS_BUILD_REVISION` stamping was found in the Replit artifact build configuration. Availability of Git metadata during the published build remains unverified. The deployment was active at the time of inspection, but its exact source revision was not identifiable.


## Published runtime and Professor readiness audit (18 November 2026)

A second read-only audit checked Replit's Development and Production configuration through a presence-only view. No values were displayed. The following settings were absent in both environments:

- Provider settings: `ATLAS_LLM_PROVIDER`, `ATLAS_LLM_CHAT_COMPLETIONS_URL`, `ATLAS_LLM_MODEL`, `ATLAS_LLM_API_KEY`
- Tenant and identity settings: `ATLAS_TENANT_DATA_DB_PATH`, `ATLAS_MEMBERSHIP_DB_PATH`, `ATLAS_OIDC_ISSUER`, `ATLAS_OIDC_AUDIENCE`, `ATLAS_OIDC_JWKS_URI`, `ATLAS_OIDC_ALLOWED_ALGORITHMS`, `ATLAS_OIDC_CLIENT_ID`, `ATLAS_OIDC_REDIRECT_URI`

This list describes the GitHub Professor configuration contract, not necessarily every variable used by the distinct Replit runtime. The Replit code's optional OpenAI service adapter uses a different configuration family (`ATLAS_ENABLE_PAID_AI`, `ATLAS_ENABLE_OPENAI`, `OPENAI_API_KEY`, and model configuration); those settings' presence was not inspected and their values were not read.

The published Replit deployment was reported as successful and public. Read-only requests to `/api/healthz` and `/api/health` returned HTTP 200 JSON health responses. This establishes API availability only, not Professor/provider readiness or source revision identity.

The Replit API artifact runs its own Node gateway and Python application (`app.main:app`). It does not expose the authenticated GitHub Professor conversation route `/professor/conversation`. Its current Professor chat submit path returns a local unavailable notice without calling the generic `/api/chat` endpoint, the optional OpenAI adapter, or the Brain. The existing generic chat endpoint is a separate service-key-protected, single-message interface without conversation IDs or persisted multi-turn model history. Its transcript remains in browser component memory.

Consequently:
- A real provider round-trip is **not verified**.
- A genuine multi-turn model conversation is **not implemented in the inspected Replit chat path**.
- A successful health response is not proof that the Professor is usable.
- The exact deployed source SHA remains unknown because the published API does not expose build metadata.
- No files, environment settings, secrets, remotes, workflows, or deployments were changed during this audit.

## Manifest tooling validation

The five focused tests for `tools/source_manifest.py` passed in an isolated local Git fixture (5 passed). They cover committed-blob hashing and deterministic output, executable modes, symlink-target hashing without following links, sensitive/generated-path exclusion and non-disclosure, dirty-worktree reporting, and Git LFS pointer handling.

PR #65 also carries the same read-only `.github/workflows/tests.yml` workflow already used by the active worker branch, with actions pinned to full commit SHAs and only `contents: read` permission. No GitHub Actions run has yet been observed for PR #65's latest head after the API-authored commits. The local five-test result is not being represented as exact-head CI.

## Safe integration sequence

### 1. Preserve immutable source snapshots

Before any migration, export or otherwise obtain read-only snapshots of both source trees. The draft PR #65 now includes `tools/source_manifest.py`, a standard-library-only manifest generator that reads the committed Git HEAD tree (not mutable working files), records sorted paths, Git modes, object IDs, byte sizes and SHA-256 hashes, and reports branch, HEAD, tracked-worktree cleanliness and untracked-file count. It hashes symlink targets without following them and records Git LFS pointer blobs without fetching payloads. Obvious secret-bearing, generated and runtime-data paths are listed with an exclusion reason and are never read or hashed. Five regression tests cover determinism, executable modes, symlinks, exclusions/non-disclosure, dirty worktrees and LFS pointers. The script can be run in either checkout once made available there; it has not yet been run against the Replit workspace. Keep both original source trees and Git histories untouched.

Do not include live secrets, credentials, private environment values, deployment tokens, or production data in the repository snapshot. Record only the names of required configuration variables, never their values.

### 2. Produce a complete collision report

For every path, classify it as:

- Replit-only
- GitHub-only
- Same path and byte-identical
- Same path but different content
- Generated, ignored, or environment-specific
- Secret-bearing or otherwise excluded from source control

The four same-name/different-content paths require explicit human review. The separate `atlas_media/init.py` and `atlas_media/__init__.py` files must remain distinct. No automated overwrite or "take newest" rule is acceptable.

### 3. Choose an integration layout

Propose a repository layout that preserves the web and API artifact boundaries and all Replit-specific modules. Prefer a clearly named runtime subtree or a deliberate monorepo layout over copying Replit files into the GitHub root. Validate Replit's expected working directory, artifact paths, build commands, and deployment configuration against that layout before adopting it.

Do not assume that moving files into a subdirectory is compatible with the existing Replit deployment. Prove the build from a clean checkout first.

### 4. Integrate on isolated branches

Create a dedicated migration branch from the authoritative GitHub base. Import source in reviewable groups, preserving original files and recording any intentional adaptation. Keep the GitHub Professor implementation and Replit runtime implementation separate until their responsibilities and dependencies have been compared.

Do not add a remote to the existing Replit workspace, rewrite its history, force-push, or merge migration work into `main` during the import.

### 5. Verify both artifacts from the GitHub checkout

From a clean checkout of the proposed GitHub integration branch:

- Install dependencies using the repository's declared lockfiles and supported package manager.
- Build the web artifact using its declared production build.
- Build the API artifact using its declared production build.
- Run the existing test suites and add focused tests for any changed artifact boundaries.
- Confirm the API gateway proxies the build-info request to the Python API, not the web catch-all.
- Confirm both web and API build metadata report the same validated full Git SHA and never echo malformed input.
- Confirm no secrets, production data, payment activation, or worker activation are required for the build.

### 6. Verify deployment separately

Only after code review and explicit owner approval should the deployment source be changed. Keep a rollback point and verify the published API route and web artifact independently. A successful publish or health endpoint is not proof of the source revision; compare the reported deployed SHA with the reviewed GitHub commit.

## Acceptance criteria

- A complete, reproducible file manifest exists for both source trees.
- Every path collision is classified and reviewed.
- All Replit-only runtime functionality is preserved.
- The proposed monorepo layout builds from a clean GitHub checkout.
- Automated tests pass on the exact proposed PR head.
- The GitHub build-revision endpoint passes exact-head CI; the Replit API gateway is separately verified to expose the route and report the deployed reviewed full Git SHA after deliberate source integration.
- No deployment, secret, payment, production-data, or worker setting changes occur without explicit approval.

## Current next action

Run the new manifest generator against the authoritative GitHub checkout and obtain an equivalent complete manifest from the Replit workspace. Compare the two manifests mechanically, then review every path collision and exclusion before proposing an integration layout. PR #64 already contains the GitHub build-revision endpoint; it must remain a draft until its worker and source-reconciliation gates are reviewed. The Replit API still returns 404 for `/api/build-info`, so deployed revision proof remains open. Until both manifests and a clean-checkout integration plan exist, do not copy, overwrite, merge, add remotes, or publish either source tree.
