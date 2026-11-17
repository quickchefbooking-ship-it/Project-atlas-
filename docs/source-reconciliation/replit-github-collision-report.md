# Replit/GitHub path collision and inventory report

**Date:** 17 November 2026  
**Comparison target:** GitHub `main` at `32471ea720edb5f10ca51aafaf9d45113d4e736c`  
**Method:** read-only path and content comparison; SHA-256 computed from file contents  
**No source files, refs, remotes, settings, secrets, or deployments were changed.**

## Five same-name, different-content paths

All five shared paths differ materially. Sizes are bytes.

| Path | Replit bytes | Replit SHA-256 | GitHub bytes | GitHub SHA-256 | Why wholesale replacement is unsafe |
|---|---:|---|---:|---|---|
| `.env.example` | 3,752 | `3052f7a711d3df5fe99720aa72c63f5b48d1eaf2aa98e321aeedafd3734e1a07` | 2,619 | `7ed1c27a2543098d21b04a4fe75725655bf7417698887a87b223e70a2fc7c94d` | Replit has an environment setup template; GitHub's file contains project overview text. Replacing Replit's file would lose its setup guidance. |
| `README.md` | 28,408 | `010af7c916ac41628d34bf04a33daf97675dd1d31b21e352b27a2281b5b0fae1` | 146 | `eb0eb384eaa985e8771a1f2837c67943a6efb937d0bd8cc35c26ddefddedf728` | Replit has platform/project documentation; GitHub's file is a short dependency list. Replacing it would discard Replit documentation. |
| `atlas_media/__init__.py` | 149 | `44ff9c4ae957d67c5c246123fee044e0ca2a4efc2fe2cc9ed68d5f80103b1509` | 256 | `c396354426dc2df8b79d5d602a82d5c0f079445fd0e481ad2c6c96a22b48a75b` | Replit exports image/video helper functions; GitHub's file contains environment-template-style assignments rather than those Python exports. Replacing it risks breaking package imports. |
| `atlas_media/generate.py` | 1,600 | `6f8cad548bcac2344e957f85cdf72a2ebe011f20f763ba5a3d9d8dd0735a0f66` | 2,300 | `edb7c0ddf97028f898b053c8a5bd2eac907978dda86fb023d3c8959dfc45f46` | Replit provides a wrapper around its managed media service; GitHub has a separate generation implementation. Replacing it risks breaking Replit callers and expected behavior. |
| `atlas_media/video.py` | 13,875 | `f51d87bd15f8125dc8a411a38b4024a0c82fcb9ccb4c41a07f212afdfc60db25` | 424 | `ec14130b8fba56001cf9a0c082b0676364c81635057fb1f7f7a3110900787fa4` | Replit implements bounded local FFmpeg video assembly; GitHub's version is a short gTTS voice-synthesis module. These are different capabilities. |

## Replit-only path inventory

The full tracked-path comparison found 841 Replit-only paths. The classification below is based on path and file-extension rules, not a semantic review of every file.

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

A path-name scan found `.env.example` as the only env/credential-like project path; it is a template. Replit Secrets were not inspected, and no credential values were read or printed. A filename scan is not proof that secrets are absent from the Replit Secrets store.

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

The two trees are not safe drop-in replacements for one another. Reconciliation must be based on complete path manifests and deliberate module mapping, not filename equality or modification time. In particular, the five shared paths require explicit adaptation decisions. No copy, overwrite, remote change, build, test, or deployment was performed during this inventory.
