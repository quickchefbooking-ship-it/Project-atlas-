# AtlasOnePro source reconciliation and safe import plan

**Status:** manifest generator, exact-path comparator and regression tests prepared on draft PR #65; full Replit CSV persistence and source-tree migration outstanding  
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

- Five exact path names are shared by the two trees; all five have materially different contents.
- 841 paths are Replit-only.
- 17 paths are GitHub-only.
- The histories have not been reconciled; a shared Git ancestor has not been established.

The earlier inventory incorrectly rendered the Replit initializer path without its literal double underscores. Exact membership checks against the Replit CSV confirm that atlas_media/__init__.py is present and atlas_media/init.py is absent. The Replit file is 149 bytes; the GitHub file at the same exact path is 256 bytes. This is a fifth same-name/different-content collision, not two distinct paths.

**Manifest status:** the complete GitHub main manifest is recorded at docs/source-reconciliation/github-main-manifest.json. It was generated from a clean checkout of commit 32471ea720edb5f10ca51aafaf9d45113d4e736c: 22 tracked entries, 22 content hashes, zero exclusions, no unreadable objects, and overall manifest SHA-256 c40e687f0d044dac998cb4a92440b983b003635b5c6cd4724c0113b503017dd2. The Replit-side CSV was verified from workspace HEAD 1cf8d1151c894bb45c1a32f4829d1945fec26d2 on branch main: clean tracked worktree, 846 rows, 760 hashed, 86 excluded, zero symlinks, no unreadable objects, 104,987 bytes, and CSV SHA-256 11c749dd4798bd285d1e83e8909e4e6be7e4441dd088347cf0e73452889fd09b. The file remains at /tmp/atlas-head-manifest.csv in the Replit container and is not yet persisted in GitHub. A read-only exact-string comparison against all 22 GitHub paths found five shared paths (all content-different), 17 GitHub-only paths, and 841 Replit-only paths. The five collisions are listed in the collision report. The sensitive .npmrc path was excluded without reading or hashing its contents; the other 85 exclusions are generated/runtime/test-evidence artifacts.

Representative Replit-specific areas that must be preserved include:

- `.replit` and the artifact configuration under `artifacts/**/.replit-artifact/`
- `artifacts/project-atlas/**` (web application and web server)
- `artifacts/api-server/**` (API gateway and Python runtime bridge)
- `app/main.py`, `app/transport.py`, and `app/domain.py`
- Replit-specific Brain, Professor, learning, workspace, and Trading 212 modules
- `package.json`, `pnpm-workspace.yaml`, `pyproject.toml`, `uv.lock`, and `scripts/build-api-production.sh`

Representative GitHub-only areas include `app.py`, `atlas_engine/**`, `atlas_media/**`, `requirements.txt`, and the GitHub repository's tests. These must not be treated as replacements for similarly named Replit modules.

**Exact-path comparison correction:** the Replit CSV was queried using exact Python string equality against all 22 literal GitHub main paths. The CSV's exact initializer path was independently checked using UTF-8 hex: it is atlas_media/__init__.py (23 bytes as a path string), not atlas_media/init.py. The exact comparison found five shared names, all five content-different; 17 GitHub paths are absent from Replit, leaving 841 Replit-only paths. An earlier response rendered double underscores incorrectly and must be disregarded. Never normalize, strip underscores, case-fold, or otherwise rewrite paths. The full CSV remains in the Replit container and is not yet persisted in GitHub, so the complete 846-row comparison still needs to be run from the committed artifact.

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

The five focused tests for `tools/source_manifest.py` passed locally in an isolated Git fixture and then passed on GitHub Actions run #2174 at commit `ddd0662b6cd29d80b9ce4a609fc24c96762c510b` (5 passed). They cover committed-blob hashing and deterministic output, executable modes, symlink-target hashing without following links, sensitive/generated-path exclusion and non-disclosure, dirty-worktree reporting, and Git LFS pointer handling.

GitHub Actions run #2176 at commit `4bc9e7841c8d346e52368ab837f047c17ef8a34f` also completed successfully. It generated the authoritative GitHub `main` manifest from a clean checkout and ran the same five regression tests (5 passed). The resulting complete manifest is committed at `docs/source-reconciliation/github-main-manifest.json`. PR #65 adds tools/compare_source_manifests.py, which compares the Replit CSV schema with the GitHub JSON manifest using exact path-string equality, verifies manifest integrity inputs, separates content differences from mode-only differences, and marks excluded entries uncomparable. Five new regression tests cover the literal double-underscore initializer path, content collisions, mode-only changes, excluded entries, duplicate paths, dirty snapshots, and CSV digest validation. Exact-head GitHub Actions run #44218984180 at commit 3378eed85d05a451d9c0de1b0522e8b1b2aae5a3 passed; the workflow generated the authoritative GitHub main manifest and completed both source-manifest regression test modules successfully.

### Baseline dependency and path-mapping finding

A full-suite CI attempt on the main-based PR branch failed before tests started because `pip install -r requirements.txt` interpreted the first line, `import os`, as an invalid package requirement. Read-only inspection confirms that GitHub `main` has several misassigned root files: `requirements.txt` contains application source, `app.py` contains media-generation tests, `README.md` contains dependency pins, and `tests/test_learning_engine.py` contains a dependency list.

This is already being repaired in the existing foundational draft PR #1, `atlas/repair-baseline-2026-11-12`; do not create a duplicate dependency/path-remapping PR. Its patch moves the application into `app.py`, restores a pinned `requirements.txt`, restores the project README, and places the affected tests and media implementation in their proper modules. Current exact PR head is `f8d6eac412d1031430bee6b3740dc67113b854ec`; GitHub Actions run `43489002177` completed successfully, including dependency installation and the test step. The PR remains draft and unmerged, so GitHub `main` itself is still unchanged.

PR #65's dedicated source-manifest workflow remains intentionally independent: it installs only the pinned test runner and validates the manifest tools without pretending to validate the unrepaired main baseline. Resolve the baseline through the existing PR #1 review path; keep full Replit source reconciliation separate.

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

The five same-name/different-content paths require explicit human review, including `atlas_media/__init__.py`. No automated overwrite or "take newest" rule is acceptable.

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

## Current next action — fresh workspace check (18 November 2026, approximately 05:40 UTC)

A new read-only inspection of the Replit app `ATLAS` reports:

- Workspace branch: `main`
- Current workspace HEAD: `c6bf5686e5ae7f0e66ce113caa506676b46b1382`
- Tracked worktree: clean
- Committed Git tree metadata: 853 tracked blobs, 0 tracked symlinks, 9,194,406 total tracked bytes
- The previous `/tmp/atlas-head-manifest.csv` is absent at this HEAD. Its historical 846-row count, 760 hashes, 86 exclusions, byte count and CSV digest are not current evidence and must not be reused.
- No fresh full manifest was generated. Hashed/excluded counts, unreadable-object count and a current full-manifest digest therefore remain unknown.
- The Replit Agent reports no active task in the current task state; previous queued tasks may still be pending.

### Targeted exact-path comparison (not a full manifest)

GitHub `main` remains identical to the manifest source commit `32471ea720edb5f10ca51aafaf9d45113d4e736c`; its 22-entry manifest SHA-256 remains `c40e687f0d044dac998cb4a92440b983b003635b5c6cd4724c0113b503017dd2`.

A read-only exact-string membership and hash comparison of those 22 GitHub paths against the current Replit committed tree found:

- 5 exact shared paths, all 5 content-different
- 0 identical paths
- 0 mode-only differences
- 0 excluded/uncomparable entries among the 5 shared paths
- 17 GitHub paths absent from Replit
- 848 Replit-only paths (853 total tracked paths minus 5 shared paths)

The five shared paths are `.env.example`, `README.md`, `atlas_media/__init__.py`, `atlas_media/generate.py`, and `atlas_media/video.py`. The initializer spelling was independently checked using the Git tree's exact UTF-8 path bytes: `atlas_media/__init__.py` is present (149 bytes; SHA-256 `44ff9c4ae957d67c5c246123fee044e0ca2a4efc2fe2cc9ed68d5f80103b1509`), while `atlas_media/init.py` is absent. `atlas_engine/__init__.py` is absent. Do not trust Markdown-rendered path strings when double underscores may be hidden; compare exact Git path bytes.

This targeted check does not replace the complete 853-row Replit manifest, does not establish the current exclusion count, and does not satisfy the full comparison acceptance criterion.

### Deployment evidence boundary

The Replit deployment lifecycle currently reports `success` at `https://wwe.atlasonepro.com`. This confirms only the lifecycle status. It does not identify the deployed commit SHA or prove GitHub/Replit source parity. A current route-level health/build-info check and deployed revision identity were not established in this inspection.

### Export limitation and next step

The Replit Agent reports that it cannot return a downloadable manifest attachment through the read-only query channel without creating a workspace-relative file. No such file was created, and no project source file, Git ref, remote, setting, secret or deployment was changed.

The next reconciliation prerequisite is a complete metadata-only CSV for this exact Replit HEAD, using the PR #65 comparator schema:
`path,mode,bytes,sha256,status,exclusion_reason`.

Sensitive paths must be classified before reading any blob content; excluded content must never be read or hashed; symlinks must not be followed; path strings must remain exact. The CSV must be transferred through an approved export path or supplied as an attachment, then validated and compared against the 22-entry GitHub manifest. Until that full manifest and collision review exist, do not copy or overwrite source files, add remotes, rewrite history, merge migration work, or publish either source tree.


## Fresh read-only architecture map — 18 November 2026

**Workspace HEAD:** `c6bf5686e5ae7f0e66ce113caa506676b46b1382` (clean tracked worktree). This map is from a metadata/configuration inspection; no tests, builds, or runtime checks were performed.

### Web artifact

- Artifact configuration: `artifacts/project-atlas/.replit-artifact/artifact.toml`; path-routed at `/`.
- Development: `pnpm --filter @workspace/project-atlas run dev`.
- Production build: `pnpm --filter @workspace/project-atlas run build`.
- Production serve: `pnpm --filter @workspace/project-atlas run serve`.
- Entry: `artifacts/project-atlas/index.html` → `src/main.tsx` → `src/App.tsx`.
- Vite output: `artifacts/project-atlas/dist/public`; static server in `server.mjs`.
- The static web server does not proxy API requests; the frontend client uses same-origin `/api/...` paths.

### API artifact and Python bridge

- Artifact configuration: `artifacts/api-server/.replit-artifact/artifact.toml`; path-routed at `/api` and the declared connector discovery path.
- Development: `pnpm --filter @workspace/api-server run dev`.
- Production build: `bash scripts/build-api-production.sh`.
- Production run: `node --enable-source-maps artifacts/api-server/dist/index.mjs`.
- Node entry: `artifacts/api-server/src/index.ts`; it verifies the managed Python runtime, starts Uvicorn on loopback, waits for Python health, then exposes the gateway.
- FastAPI entry: `app/main.py`, composed through `app/transport.py`.
- The Node gateway is the Replit production process and manages the Python child process; this is not the same as the GitHub root `app.py` application.
- `scripts/build-api-production.sh`, `pyproject.toml`, and `uv.lock` govern the Python build; the managed runtime contract requires Python 3.12 or newer.

### Shared build configuration

- `package.json`, `pnpm-workspace.yaml`, and `pnpm-lock.yaml`: JavaScript workspace and root scripts.
- `tsconfig.json` and `tsconfig.base.json`: TypeScript configuration.
- `pyproject.toml` and `uv.lock`: managed Python dependency contract.
- `.replit`: deployment/router configuration; environment-section values were not inspected.
- `Dockerfile`, `compose.yaml`, and `compose.providers.yaml`: container alternatives, separate from the artifact run path.
- `artifacts/mockup-sandbox/`: component-preview artifact.

### Module families

- `app/`: Python domain/application, transport, identity/workspace security, Brain/learning, market/paper/trading, media and connector modules.
- `artifacts/project-atlas/`: web UI, static server and frontend tests.
- `artifacts/api-server/`: Node gateway, Python bridge, fixtures and API tests.
- `atlas_media/`: media helpers.
- `lib/`: shared API clients, schemas and database packages.
- `services/professor-gateway/`: separate package; disabled by default and not declared as a separately routed Replit artifact in the inspected manifests.
- `scripts/`, `tests/`, and `benchmarks/`: build, verification and test support.

### Clean-checkout validation sequence

1. Confirm both artifact manifests, root workspace files, `app/`, and the API build script are present in the proposed GitHub integration commit.
2. Install JavaScript dependencies from the root lockfile with frozen resolution; typecheck and build the web artifact, then start its static server.
3. Build the API artifact using the declared Node, pnpm, uv and managed Python requirements; confirm the bundled Node gateway and managed Python environment.
4. Start the API production process and verify Node-to-FastAPI health on loopback and public `/api/healthz`.
5. Verify path routing from a clean checkout: `/` reaches web; `/api/...` and the declared discovery route reach the API; unmatched paths do not fall through to the web shell or unrelated API routes.
6. Validate packaging context, persistence and database assumptions separately from Docker and Professor gateway packages.
7. Record build/test results and deployed-revision identity separately; this map does not prove the published Replit deployment serves this HEAD.

This architecture map is a planning artifact only. The full Replit path manifest has not been transferred, source import has not begun, and no workspace or deployment change has occurred.
