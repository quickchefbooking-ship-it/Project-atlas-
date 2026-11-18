# Replit/GitHub path collision and inventory report

**Date:** 18 November 2026  
**Comparison target:** GitHub main at 32471ea720edb5f10ca51aafaf9d45113d4e736c  
**Replit snapshot:** main at 1cf8d1151c894bb45c1a32f4829d1945fec26d2  
**Method:** exact path-string comparison and SHA-256 metadata only; source contents were not transferred  
**No source files, refs, remotes, settings, secrets, or deployments were changed.**

## Manifest evidence

The Replit CSV manifest contains 846 rows, is 104,987 bytes, and has SHA-256:

`11c749dd4798bd285d1e83e8909e4e6be7e4441dd088347cf0e73452889fd09b`

It reports 760 hashed entries, 86 excluded entries, zero symlinks, no unreadable objects, and a clean tracked worktree. The file remains at `/tmp/atlas-head-manifest.csv` in the Replit container and has not yet been persisted in GitHub.

A read-only query compared the CSV path column against all 22 exact GitHub main paths using Python string equality. It found five shared names, all five with different content; 17 GitHub paths absent from Replit; and 841 Replit-only paths. The full 846-row CSV still needs a safe transfer so the complete comparison can be committed and reproduced. No path normalization, case-folding, underscore stripping, or basename matching is permitted.

## Five same-name, different-content paths

The five exact shared path names all have materially different content. Sizes are bytes.

| Exact path | Replit bytes | Replit SHA-256 | GitHub bytes | GitHub SHA-256 | Why wholesale replacement is unsafe |
|---|---:|---|---:|---|---|
| `.env.example` | 3,752 | `3052f7a711d3df5fe99720aa72c63f5b48d1eaf2aa98e321aeedafd3734e1a07` | 2,619 | `7ed1c27a2543098d21b04a4fe75725655bf7417698887a87b223e70a2fc7c94d` | Replit has an environment setup template; GitHub's file contains project overview text. Replacing Replit's file would lose its setup guidance. |
| `README.md` | 28,408 | `010af7c916ac41628d34bf04a33daf97675dd1d31b21e352b27a2281b5b0fae1` | 146 | `eb0eb384eaa985e8771a1f2837c67943a6efb937d0bd8cc35c26ddefddedf728` | Replit has platform/project documentation; GitHub's file is a short dependency list. Replacing it would discard Replit documentation. |
| `atlas_media/__init__.py` | 149 | `44ff9c4ae957d67c5c246123fee044e0ca2a4efc2fe2cc9ed68d5f80103b1509` | 256 | `c396354426dc2df8b79d5d602a82d5c0f079445fd0e481ad2c6c96a22b48a75b` | The exact path is shared, but the package initializer contents differ. The earlier inventory incorrectly rendered the Replit name without its double underscores. |
| `atlas_media/generate.py` | 1,600 | `6f8cad548bcac2344e957f85cdf72a2ebe011f20f763ba5a3d9d8dd0735a0f66` | 2,300 | `edb7c0ddf97028f898b053c8a5bd2eac907978dda86fb023d3c8959dfc45f46` | Replit provides a wrapper around its managed media service; GitHub has a separate generation implementation. Replacing it risks breaking Replit callers and expected behavior. |
| `atlas_media/video.py` | 13,875 | `f51d87bd15f8125dc8a411a38b4024a0c82fcb9ccb4c41a07f212afdfc60db25` | 424 | `ec14130b8fba56001cf9a0c082b0676364c81635057fb1f7f7a3110900787fa4` | Replit implements bounded local FFmpeg video assembly; GitHub's version is a short gTTS voice-synthesis module. These are different capabilities. |

## Initializer path correction

The Replit CSV confirms the exact initializer path `atlas_media/__init__.py` (UTF-8 path length 23 bytes). The exact path `atlas_media/init.py` is absent. The Replit row has 149 bytes and SHA-256 `44ff9c4ae957d67c5c246123fee044e0ca2a4efc2fe2cc9ed68d5f80103b1509`; the GitHub row at the same exact path has 256 bytes and SHA-256 `c396354426dc2df8b79d5d602a82d5c0f079445fd0e481ad2c6c96a22b48a75b`.

An earlier response stripped the double underscores when rendering the path, which led to the false conclusion that these were distinct filenames. The base64/hex checks against the CSV and exact set-membership checks establish that this is a fifth same-name/different-content collision.

## Replit-only path inventory

The read-only tree inventory reports 846 tracked Replit paths and 22 tracked GitHub paths. With five shared path names, the corrected counts are 841 Replit-only paths and 17 GitHub-only paths. The prefix classification below is based on path and file-extension rules, not a semantic review of every file.

**Manifest limitation:** the complete machine-readable CSV has not yet been persisted in this PR. The counts and grouped inventory are supported by the verified CSV metadata and exact comparison of all 22 GitHub path names, but the full 841-name Replit-only list and all 86 exclusion records remain to be committed and reviewed.

| Replit-only prefix | Files | Source | Config | Tests | Generated | Docs/other |
|---|---:|---:|---:|---:|---:|---:|
| `artifacts/project-atlas` | 201 | 159 | 5 | 35 | 0 | 2 |
| `app` | 120 | 119 | 1 | 0 | 0 | 0 |
| `tests` | 114 | 0 | 0 | 114 | 0 | 0 |
| `lib` | 83 | 75 | 8 | 0 | 0 | 0 |
| `artifacts/api-server` | 72 | 19 | 12 | 38 | 0 | 3 |
| `artifacts/mockup-sandbox` | 72 | 67 | 5 | 0 | 0 | 0 |
| `docs` | 66 | 0 | 3 | 0 | 0 | 63 |
| Root files | 46 | 1 | 16 | 0 | 0 | 29 |
| `.agents` | 35 | 0 | 0 | 0 | 0 | 35 |
| `scripts` | 18 | 15 | 3 | 0 | 0 | 0 |
| `benchmarks` | 6 | 3 | 2 | 0 | 0 | 1 |
| `services` | 6 | 3 | 2 | 1 | 0 | 0 |
| `.github` | 1 | 0 | 1 | 0 | 0 | 0 |
| `atlas_media` | 1 | 1 | 0 | 0 | 0 | 0 |
| **Total** | **841** | **462** | **58** | **188** | **0** | **133** |

The Replit-only set includes the React/Vite web application, Express API gateway, Python backend, Brain/Professor/learning/workspace features, tests, scripts, deployment configuration, and documentation. All these areas must be mapped before any import.

## GitHub-only paths

The 17 GitHub-only paths are:

- `app.py`
- `atlas_engine/__init__.py`
- `atlas_engine/config.py`
- `atlas_engine/evaluator.py`
- `atlas_engine/executor.py`
- `atlas_engine/improvement.py`
- `atlas_engine/learning_memory.py`
- `atlas_engine/safe_testing.py`
- `atlas_engine/storage.py`
- `atlas_engine/task_manager.py`
- `atlas_media/audio.py`
- `atlas_media/sources.py`
- `index.html.`
- `requirements.txt`
- `sample_task.py`
- `tests/test_learning_engine.py`
- `tests/test_media_generation.py`

## Generated and secret-like paths

The Replit CSV reports 86 excluded entries. The `.npmrc` path was explicitly excluded as sensitive credential configuration without reading or hashing its contents. The other 85 exclusions are generated/runtime/test-evidence artifacts. The `.env.example` file is a template; Replit Secrets were not inspected, and no credential values were read or printed. A filename scan is not proof that secrets are absent from the Replit Secrets store.

No compiled-output, bytecode, or runtime-database paths matched the generated-file rule among the 841 tracked Replit-only paths. Generated/runtime paths outside that tracked set include:

- `artifacts/api-server/dist/**`
- `artifacts/project-atlas/dist/public/**`
- `artifacts/mockup-sandbox/dist/**`
- `app/pycache/*.pyc` and `artifacts/api-server/python/pycache/*.pyc`
- `generated-artifacts/**`
- `artifacts/api-server/data/atlas.sqlite3`
- `artifacts/api-server/data/atlas-users/*.sqlite3`

Only paths were inspected for these generated/runtime locations; file contents were not read.

## Conclusion

The two trees are not safe drop-in replacements for one another. Reconciliation must be based on complete manifests and deliberate module mapping, not filename equality or modification time. All five same-name/different-content paths require explicit adaptation decisions. No copy, overwrite, remote change, build, test, or deployment was performed during the original inventory.


## Fresh workspace checkpoint — 18 November 2026, 06:39 UTC

This section supersedes the older Replit snapshot counts above for the fresh workspace HEAD. The older complete CSV was not present, and the new complete CSV remains in memory only.

- Replit branch: `main`
- Replit HEAD: `c6bf5686e5ae7f0e66ce113caa506676b46b1382`
- Tracked worktree: clean
- Tracked paths: 853
- Hashed paths: 852
- Excluded before reading or hashing: 1 sensitive credential configuration path (its content was not read or hashed)
- Unreadable objects: 0
- Symlinks: 0
- Total tracked bytes: 9,194,406
- Metadata CSV: 108,926 bytes; SHA-256 `f0954b6c578290474d6c1ffa0b649425262de7a27754ee2ee0f821f18ee1f2b6`

The five exact shared path names remain the same and each current Replit hash differs from the GitHub main snapshot. The targeted comparison below is against the 22-path GitHub manifest snapshot at `32471ea720edb5f10ca51aafaf9d45113d4e736c`, not a full 853-row reconciliation:

| Exact path | Replit bytes | Replit SHA-256 | GitHub bytes | GitHub SHA-256 |
|---|---:|---|---:|---|
| `.env.example` | 3,752 | `3052f7a711d3df5fe99720aa72c63f5b48d1eaf2aa98e321aeedafd3734e1a07` | 2,619 | `7ed1c27a2543098d21b04a4fe75725655bf7417698887a87b223e70a2fc7c94d` |
| `README.md` | 28,408 | `010af7c916ac41628d34bf04a33daf97675dd1d31b21e352b27a2281b5b0fae1` | 146 | `eb0eb384eaa985e8771a1f2837c67943a6efb937d0bd8cc35c26ddefddedf728` |
| `atlas_media/__init__.py` | 149 | `44ff9c4ae957d67c5c246123fee044e0ca2a4efc2fe2cc9ed68d5f80103b1509` | 256 | `c396354426dc2df8b79d5d602a82d5c0f079445fd0e481ad2c6c96a22b48a75b` |
| `atlas_media/generate.py` | 1,600 | `6f8cad548bcac2344e957f85cdf72a2ebe011f20f763ba5a3d9d8dd0735a0f66` | 2,300 | `edb7c0ddf97028f898b053c8a5bd2eac907978dda86fb023d3c8959dfc45f46` |
| `atlas_media/video.py` | 13,875 | `f51d87bd15f8125dc8a411a38b4024a0c82fcb9ccb4c41a07f212afdfc60db25` | 424 | `ec14130b8fba56001cf9a0c082b0676364c81635057fb1f7f7a3110900787fa4` |

From the limited exact-path comparison, 848 Replit paths are Replit-only and 17 GitHub paths are GitHub-only; the five shared paths are content collisions. The complete 853-row manifest, including all exclusions, is still required to reproduce the comparison and review every path. No source transfer or workspace modification was performed.


## Fresh exact-path comparison — 18 November 2026, 09:50 UTC

The current Replit workspace was rechecked read-only at the same HEAD `c6bf5686e5ae7f0e66ce113caa506676b46b1382`; the tracked worktree remains clean.

- Tracked entries: 853
- Hashed entries: 852
- Excluded entries: 1 (path and content not disclosed or read)
- Unreadable entries: 0
- Symlinks: 0

An in-memory exact-path comparison was run against the complete supplied GitHub main snapshot at `32471ea720edb5f10ca51aafaf9d45113d4e736c` (22 hashed paths):

| Result | Count |
|---|---:|
| Shared exact paths | 5 |
| Identical content | 0 |
| Content-different | 5 |
| Mode-only differences | 0 |
| Uncomparable | 0 |
| Replit-only | 848 |
| GitHub-only | 17 |

The excluded path does not intersect the GitHub path set. No source contents were read or transferred.

The five collisions remain `.env.example`, `README.md`, `atlas_media/__init__.py`, `atlas_media/generate.py`, and `atlas_media/video.py`. A Replit Agent text response rendered the initializer path without its literal double underscores; an exact-string recheck returned JSON-escaped `atlas_media/\u005f\u005finit\u005f\u005f.py` and UTF-8 hex `61746c61735f6d656469612f5f5f696e69745f5f2e7079`, confirming the literal path is `atlas_media/__init__.py`. Its Replit metadata remains 149 bytes, mode `100644`, SHA-256 `44ff9c4ae957d67c5c246123fee044e0ca2a4efc2fe2cc9ed68d5f80103b1509`; GitHub main is 256 bytes, mode `100644`, SHA-256 `c396354426dc2df8b79d5d602a82d5c0f079445fd0e481ad2c6c96a22b48a75b`.

This is a full exact-path comparison against the 22-entry GitHub snapshot performed in memory; the full Replit manifest itself has not been transferred or persisted. No source integration or workspace modification occurred.


## Public-repository transfer gate

The authoritative GitHub repository is public. The complete sanitized Replit manifest contains path names and hashes for 852 Replit tracked files, including Replit-only/internal project structure. Although it contains no source contents and excludes the sensitive path, committing that full path inventory publicly is a separate disclosure decision.

Therefore the full manifest/chunk transfer is **not committed to this public repository pending owner review of the path-list disclosure**. The in-memory exact comparison against the 22 GitHub main paths is recorded above; no manifest data file was persisted and no Replit workspace file was created. The tested chunk assembler remains available for a later owner-approved transfer destination, which may be private rather than this public repository.


## Fresh hashed-only comparison checkpoint — 18 November 2026, 14:08 UTC

A fresh read-only Replit inspection and in-memory comparison was completed against the fixed GitHub main manifest at `32471ea720edb5f10ca51aafaf9d45113d4e736c`. The Replit workspace remains clean at `c6bf5686e5ae7f0e66ce113caa506676b46b1382`.

- Tracked paths: 853
- Hashed paths: 852
- Excluded before reading or hashing: 1 sensitive configuration/credential category (path and content not disclosed)
- Unreadable: 0
- Symlinks: 0
- Total tracked bytes: 9,194,406
- Canonical hashed-only manifest: 108,864 bytes; SHA-256 `af0f47b4a4c21dea697368d1e9e44937d50d94a8b68b073e36a35719262274e`

The complete hashed-only path set was compared in memory against the 22-path GitHub snapshot. Results:

| Result | Count |
|---|---:|
| Shared exact paths | 5 |
| Identical content and mode | 0 |
| Content-different | 5 |
| Mode-only | 0 |
| Uncomparable | 0 |
| Replit-only hashed paths | 847 |
| GitHub-only paths | 17 |

The excluded path does not intersect the GitHub path set. All five collisions remain the same exact paths listed above, and their metadata values match the earlier checkpoint. The initializer was independently confirmed by UTF-8 hex `61746c61735f6d656469612f5f5f696e69745f5f2e7079`, which decodes to `atlas_media/__init__.py`; `atlas_media/init.py` is absent.

The full manifest was not transferred or persisted. This update records only the aggregate comparison and already-reviewed collision metadata. The public-repository disclosure gate remains in place for the full 852-path inventory. No Replit files, Git refs, settings, secrets, or deployment were changed.
