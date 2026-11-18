"""Create a deterministic, content-safe manifest of a Git commit's tracked tree.

The manifest hashes Git blob contents (not the working directory), so dirty
workspaces are reported accurately without silently changing the snapshot.
Sensitive and generated paths are listed but never read or hashed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any


ENV_TEMPLATE_NAMES = {
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.dist",
    ".env.defaults",
}
SENSITIVE_DIRECTORY_NAMES = {".ssh", "secrets", "credentials"}
GENERATED_DIRECTORY_NAMES = {
    "__pycache__",
    "pycache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "node_modules",
    ".next",
    ".turbo",
    ".cache",
    "coverage",
    "dist",
    "build",
    "generated-artifacts",
}
RUNTIME_DIRECTORY_NAMES = {"runtime", "uploads", "logs", "tmp", "temp", "instance"}
SENSITIVE_FILE_NAMES = {
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".git-credentials",
    "credentials.json",
    "service-account.json",
    "secrets.json",
    "secret.json",
}
SENSITIVE_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".p8",
}
RUNTIME_SUFFIXES = {
    ".sqlite",
    ".sqlite3",
    ".db",
    ".db-wal",
    ".db-shm",
    ".sqlite-wal",
    ".sqlite-shm",
    ".pyc",
    ".pyo",
    ".log",
}
GIT_LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"


def _git(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def _exclusion_reason(path: str) -> str | None:
    """Classify obvious sensitive/generated/runtime paths without reading them."""
    parsed = PurePosixPath(path)
    parts = tuple(part.lower() for part in parsed.parts)
    name = parsed.name.lower()

    if any(part in SENSITIVE_DIRECTORY_NAMES for part in parts[:-1]):
        return "sensitive_directory"
    if name in SENSITIVE_FILE_NAMES or name.startswith(("id_rsa", "id_ed25519", "id_ecdsa")):
        return "credential_or_private_key"
    if name == ".env" or (
        name.startswith(".env.") and name not in ENV_TEMPLATE_NAMES
    ):
        return "environment_file"
    if any(name.endswith(suffix) for suffix in SENSITIVE_SUFFIXES):
        return "credential_or_private_key"
    if any(part in GENERATED_DIRECTORY_NAMES for part in parts[:-1]):
        return "generated_directory"
    if any(part in RUNTIME_DIRECTORY_NAMES for part in parts[:-1]):
        return "runtime_data_directory"
    if any(name.endswith(suffix) for suffix in RUNTIME_SUFFIXES):
        return "runtime_data"
    return None


def _tree_entries(root: Path) -> list[tuple[str, str, str, str]]:
    """Return (mode, object type, object SHA, path) from the committed HEAD tree."""
    raw = _git(root, "ls-tree", "-r", "-z", "--full-tree", "HEAD")
    entries: list[tuple[str, str, str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_type, object_sha = metadata.decode("ascii").split()
        entries.append((mode, object_type, object_sha, os.fsdecode(raw_path)))
    entries.sort(key=lambda item: item[3])
    return entries


def build_manifest(repo_root: str | Path) -> dict[str, Any]:
    """Build a SHA-256 manifest of the committed Git tree without exposing content."""
    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise ValueError("Repository root must be an existing directory.")

    head_sha = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    branch = _git(root, "branch", "--show-current").decode("utf-8", "replace").strip()
    tracked_status = _git(root, "status", "--porcelain=v1", "--untracked-files=no")
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    tree = _tree_entries(root)

    entries: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for mode, object_type, object_sha, path in tree:
        reason = _exclusion_reason(path)
        entry: dict[str, Any] = {
            "path": path,
            "mode": mode,
            "object_type": object_type,
            "object_sha": object_sha,
            "content_kind": "excluded" if reason else "blob",
            "size_bytes": None,
            "sha256": None,
            "excluded_reason": reason,
        }

        if object_type == "commit" or mode == "160000":
            entry["content_kind"] = "submodule"
            entry["excluded_reason"] = "submodule_content_not_in_superproject"
            entries.append(entry)
            continue

        try:
            size = int(_git(root, "cat-file", "-s", object_sha).decode("ascii").strip())
            entry["size_bytes"] = size
            if reason is None:
                content = _git(root, "cat-file", "blob", object_sha)
                entry["sha256"] = hashlib.sha256(content).hexdigest()
                if mode == "120000":
                    entry["content_kind"] = "symlink_target"
                elif content.startswith(GIT_LFS_POINTER_PREFIX):
                    entry["content_kind"] = "git_lfs_pointer"
                else:
                    entry["content_kind"] = "file"
        except (OSError, subprocess.CalledProcessError, ValueError):
            entry["content_kind"] = "unreadable"
            entry["excluded_reason"] = "git_object_unavailable"
            errors.append({"path": path, "error": "git_object_unavailable"})

        entries.append(entry)

    hashed_count = sum(entry["sha256"] is not None for entry in entries)
    excluded_count = sum(entry["excluded_reason"] is not None for entry in entries)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "head_sha": head_sha,
        "branch": branch or None,
        "clean_tracked_worktree": not bool(tracked_status),
        "untracked_file_count": len([item for item in untracked.split(b"\0") if item]),
        "tracked_entry_count": len(entries),
        "hashed_entry_count": hashed_count,
        "excluded_entry_count": excluded_count,
        "complete": not errors,
        "errors": errors,
        "entries": entries,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    payload["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write a deterministic, content-safe manifest of tracked Git files."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Git repository root (defaults to the parent of this tools directory).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON to this path; stdout is used when omitted.",
    )
    args = parser.parse_args(argv)

    try:
        manifest = build_manifest(args.repo_root)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"source manifest failed: {type(exc).__name__}", file=sys.stderr)
        return 2

    rendered = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if manifest["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
