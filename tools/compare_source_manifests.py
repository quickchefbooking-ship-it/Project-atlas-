"""Compare Replit CSV and GitHub JSON source manifests using exact path strings.

This tool compares metadata only. It never opens source files or follows paths.
Path keys are used exactly as recorded: no normalization, case-folding, or
underscore rewriting is performed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Any


CSV_COLUMNS = [
    "path",
    "mode",
    "bytes",
    "sha256",
    "status",
    "exclusion_reason",
]
SHA256_RE = re.compile(r"[0-9a-f]{64}")


def _validate_path(path: Any, source: str) -> str:
    if not isinstance(path, str) or not path:
        raise ValueError(f"{source} contains an empty or invalid path.")
    # Deliberately do not normalize, case-fold, or rewrite path characters.
    return path


def _validate_sha256(value: Any, source: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{source} contains an invalid SHA-256 digest.")
    return value


def _read_replit_csv(path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Replit manifest CSV must be UTF-8.") from exc

    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames != CSV_COLUMNS:
        raise ValueError("Replit manifest CSV header does not match the expected schema.")

    entries: dict[str, dict[str, Any]] = {}
    for line_number, row in enumerate(reader, start=2):
        if None in row:
            raise ValueError(f"Replit manifest CSV row {line_number} has extra columns.")
        path_value = _validate_path(row.get("path"), f"CSV row {line_number}")
        if path_value in entries:
            raise ValueError(f"Replit manifest CSV contains a duplicate path at row {line_number}.")

        mode = row.get("mode")
        status = row.get("status")
        if not mode or status not in {"hashed", "excluded"}:
            raise ValueError(f"Replit manifest CSV row {line_number} has invalid metadata.")

        raw_size = row.get("bytes", "")
        try:
            size_bytes = int(raw_size) if raw_size != "" else None
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Replit manifest CSV row {line_number} has an invalid byte count.") from exc
        if size_bytes is not None and size_bytes < 0:
            raise ValueError(f"Replit manifest CSV row {line_number} has a negative byte count.")

        raw_sha = row.get("sha256", "")
        sha256 = _validate_sha256(raw_sha, f"CSV row {line_number}") if raw_sha else None
        exclusion_reason = row.get("exclusion_reason") or None
        if status == "hashed" and (sha256 is None or size_bytes is None or exclusion_reason is not None):
            raise ValueError(f"Replit manifest CSV row {line_number} has inconsistent hashed metadata.")
        if status == "excluded" and (sha256 is not None or not exclusion_reason):
            raise ValueError(f"Replit manifest CSV row {line_number} has inconsistent exclusion metadata.")

        entries[path_value] = {
            "path": path_value,
            "mode": mode,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "status": status,
            "exclusion_reason": exclusion_reason,
        }

    return entries, digest


def _read_github_json(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("GitHub manifest JSON could not be read.") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("GitHub manifest has an unsupported schema.")
    if payload.get("complete") is not True:
        raise ValueError("GitHub manifest is incomplete.")
    if payload.get("clean_tracked_worktree") is not True or payload.get("untracked_file_count") != 0:
        raise ValueError("GitHub manifest must describe a clean tracked worktree with no untracked files.")
    if payload.get("errors") not in ([], None):
        raise ValueError("GitHub manifest contains unreadable Git objects.")

    expected_digest = payload.get("manifest_sha256")
    if expected_digest is not None:
        digest_payload = {key: value for key, value in payload.items() if key != "manifest_sha256"}
        canonical = json.dumps(
            digest_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        if hashlib.sha256(canonical).hexdigest() != expected_digest:
            raise ValueError("GitHub manifest integrity check failed.")

    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list) or payload.get("tracked_entry_count") != len(raw_entries):
        raise ValueError("GitHub manifest entry count is inconsistent.")

    entries: dict[str, dict[str, Any]] = {}
    for index, raw_entry in enumerate(raw_entries):
        if not isinstance(raw_entry, dict):
            raise ValueError(f"GitHub manifest entry {index} is invalid.")
        path_value = _validate_path(raw_entry.get("path"), f"GitHub entry {index}")
        if path_value in entries:
            raise ValueError("GitHub manifest contains duplicate paths.")

        mode = raw_entry.get("mode")
        size_bytes = raw_entry.get("size_bytes")
        sha256 = raw_entry.get("sha256")
        exclusion_reason = raw_entry.get("excluded_reason")
        if not isinstance(mode, str) or not mode:
            raise ValueError(f"GitHub manifest entry {index} has an invalid mode.")
        if size_bytes is not None and (not isinstance(size_bytes, int) or size_bytes < 0):
            raise ValueError(f"GitHub manifest entry {index} has an invalid byte count.")
        if sha256 is not None:
            sha256 = _validate_sha256(sha256, f"GitHub entry {index}")
            if size_bytes is None or exclusion_reason is not None:
                raise ValueError(f"GitHub manifest entry {index} has inconsistent hashed metadata.")
            status = "hashed"
        else:
            if not exclusion_reason:
                raise ValueError(f"GitHub manifest entry {index} has no hash or exclusion reason.")
            status = "excluded"

        entries[path_value] = {
            "path": path_value,
            "mode": mode,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "status": status,
            "exclusion_reason": exclusion_reason,
        }

    return entries, payload


def compare_entries(
    replit_entries: dict[str, dict[str, Any]],
    github_entries: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    replit_paths = set(replit_entries)
    github_paths = set(github_entries)
    shared_paths = sorted(replit_paths & github_paths)

    identical: list[str] = []
    content_different: list[dict[str, Any]] = []
    mode_only: list[dict[str, Any]] = []
    uncomparable: list[dict[str, Any]] = []

    for path in shared_paths:
        left = replit_entries[path]
        right = github_entries[path]
        if left["status"] != "hashed" or right["status"] != "hashed":
            uncomparable.append({
                "path": path,
                "replit_status": left["status"],
                "replit_exclusion_reason": left["exclusion_reason"],
                "github_status": right["status"],
                "github_exclusion_reason": right["exclusion_reason"],
            })
            continue

        if left["sha256"] != right["sha256"] or left["size_bytes"] != right["size_bytes"]:
            content_different.append({
                "path": path,
                "replit": {
                    "mode": left["mode"],
                    "bytes": left["size_bytes"],
                    "sha256": left["sha256"],
                },
                "github": {
                    "mode": right["mode"],
                    "bytes": right["size_bytes"],
                    "sha256": right["sha256"],
                },
                "mode_changed": left["mode"] != right["mode"],
            })
        elif left["mode"] != right["mode"]:
            mode_only.append({
                "path": path,
                "replit_mode": left["mode"],
                "github_mode": right["mode"],
            })
        else:
            identical.append(path)

    return {
        "summary": {
            "replit_entry_count": len(replit_paths),
            "github_entry_count": len(github_paths),
            "shared_path_count": len(shared_paths),
            "replit_only_count": len(replit_paths - github_paths),
            "github_only_count": len(github_paths - replit_paths),
            "identical_count": len(identical),
            "content_different_count": len(content_different),
            "mode_only_count": len(mode_only),
            "uncomparable_count": len(uncomparable),
        },
        "paths": {
            "replit_only": sorted(replit_paths - github_paths),
            "github_only": sorted(github_paths - replit_paths),
            "identical": identical,
            "content_different": content_different,
            "mode_only": mode_only,
            "uncomparable": uncomparable,
        },
    }


def build_comparison(
    replit_csv: Path,
    github_json: Path,
    replit_head: str | None = None,
    expected_replit_sha256: str | None = None,
) -> dict[str, Any]:
    replit_entries, csv_digest = _read_replit_csv(replit_csv)
    if expected_replit_sha256 is not None:
        expected = _validate_sha256(expected_replit_sha256, "expected Replit manifest digest")
        if csv_digest != expected:
            raise ValueError("Replit manifest CSV integrity check failed.")

    github_entries, github_payload = _read_github_json(github_json)
    comparison = compare_entries(replit_entries, github_entries)
    comparison["schema_version"] = 1
    comparison["replit"] = {
        "head_sha": replit_head,
        "source_file_sha256": csv_digest,
        "tracked_entry_count": len(replit_entries),
        "hashed_entry_count": sum(item["status"] == "hashed" for item in replit_entries.values()),
        "excluded_entry_count": sum(item["status"] == "excluded" for item in replit_entries.values()),
    }
    comparison["github"] = {
        "head_sha": github_payload.get("head_sha"),
        "manifest_sha256": github_payload.get("manifest_sha256"),
        "tracked_entry_count": len(github_entries),
    }
    comparison["comparison_policy"] = (
        "Exact path-string equality; no path normalization, case-folding, or underscore rewriting. "
        "Content equality uses SHA-256 and byte size; file mode is reported separately."
    )
    return comparison


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare a Replit CSV manifest with a GitHub JSON source manifest."
    )
    parser.add_argument("--replit-csv", type=Path, required=True)
    parser.add_argument("--github-json", type=Path, required=True)
    parser.add_argument("--replit-head")
    parser.add_argument("--expected-replit-sha256")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        result = build_comparison(
            args.replit_csv,
            args.github_json,
            replit_head=args.replit_head,
            expected_replit_sha256=args.expected_replit_sha256,
        )
    except (OSError, ValueError) as exc:
        print(f"manifest comparison failed: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
