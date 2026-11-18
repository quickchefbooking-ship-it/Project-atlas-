import csv
import hashlib
import json

import pytest

from tools.compare_source_manifests import build_comparison


CSV_COLUMNS = ["path", "mode", "bytes", "sha256", "status", "exclusion_reason"]


def write_replit_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_github_manifest(path, entries, *, clean=True, complete=True):
    payload = {
        "schema_version": 1,
        "head_sha": "a" * 40,
        "branch": "main",
        "clean_tracked_worktree": clean,
        "untracked_file_count": 0,
        "tracked_entry_count": len(entries),
        "hashed_entry_count": sum(entry["sha256"] is not None for entry in entries),
        "excluded_entry_count": sum(entry["sha256"] is None for entry in entries),
        "complete": complete,
        "errors": [],
        "entries": entries,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    payload["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def csv_row(path, *, mode="100644", size=10, digest="a" * 64, status="hashed", reason=""):
    return {
        "path": path,
        "mode": mode,
        "bytes": str(size) if size is not None else "",
        "sha256": digest or "",
        "status": status,
        "exclusion_reason": reason,
    }


def github_entry(path, *, mode="100644", size=10, digest="a" * 64, reason=None):
    return {
        "path": path,
        "mode": mode,
        "object_type": "blob",
        "object_sha": "b" * 40,
        "content_kind": "file" if digest else "excluded",
        "size_bytes": size,
        "sha256": digest,
        "excluded_reason": reason,
    }


def test_comparison_uses_exact_path_strings_and_finds_initializer_collision(tmp_path):
    replit_csv = tmp_path / "replit.csv"
    github_json = tmp_path / "github.json"
    write_replit_csv(
        replit_csv,
        [csv_row("atlas_media/__init__.py", size=149, digest="a" * 64)],
    )
    write_github_manifest(
        github_json,
        [
            github_entry("atlas_media/__init__.py", size=256, digest="c" * 64),
            github_entry("atlas_media/init.py", size=149, digest="a" * 64),
        ],
    )

    result = build_comparison(replit_csv, github_json)
    summary = result["summary"]

    assert summary["shared_path_count"] == 1
    assert summary["replit_only_count"] == 0
    assert summary["github_only_count"] == 1
    assert summary["content_different_count"] == 1
    assert result["paths"]["github_only"] == ["atlas_media/init.py"]
    assert result["paths"]["content_different"][0]["path"] == "atlas_media/__init__.py"


def test_comparison_reports_mode_only_difference_separately(tmp_path):
    replit_csv = tmp_path / "replit.csv"
    github_json = tmp_path / "github.json"
    write_replit_csv(
        replit_csv,
        [csv_row("scripts/run.sh", mode="100644", size=5, digest="d" * 64)],
    )
    write_github_manifest(
        github_json,
        [github_entry("scripts/run.sh", mode="100755", size=5, digest="d" * 64)],
    )

    result = build_comparison(replit_csv, github_json)

    assert result["summary"]["identical_count"] == 0
    assert result["summary"]["mode_only_count"] == 1
    assert result["paths"]["mode_only"] == [{
        "path": "scripts/run.sh",
        "replit_mode": "100644",
        "github_mode": "100755",
    }]


def test_excluded_entries_are_uncomparable_not_identical(tmp_path):
    replit_csv = tmp_path / "replit.csv"
    github_json = tmp_path / "github.json"
    write_replit_csv(
        replit_csv,
        [csv_row(
            ".npmrc",
            size=56,
            digest="",
            status="excluded",
            reason="sensitive credential configuration; content not read or hashed",
        )],
    )
    write_github_manifest(
        github_json,
        [github_entry(".npmrc", size=56, digest=None, reason="credential_or_private_key")],
    )

    result = build_comparison(replit_csv, github_json)

    assert result["summary"]["uncomparable_count"] == 1
    assert result["summary"]["identical_count"] == 0
    assert result["paths"]["uncomparable"][0]["path"] == ".npmrc"


def test_rejects_duplicate_paths_and_untrusted_github_snapshot(tmp_path):
    replit_csv = tmp_path / "replit.csv"
    github_json = tmp_path / "github.json"
    duplicate = csv_row("same.py")
    write_replit_csv(replit_csv, [duplicate, duplicate])
    write_github_manifest(github_json, [github_entry("same.py")])

    with pytest.raises(ValueError, match="duplicate path"):
        build_comparison(replit_csv, github_json)

    write_replit_csv(replit_csv, [csv_row("same.py")])
    write_github_manifest(github_json, [github_entry("same.py")], clean=False)

    with pytest.raises(ValueError, match="clean tracked worktree"):
        build_comparison(replit_csv, github_json)


def test_rejects_manifest_digest_mismatch(tmp_path):
    replit_csv = tmp_path / "replit.csv"
    github_json = tmp_path / "github.json"
    digest = write_replit_csv(replit_csv, [csv_row("same.py")])
    write_github_manifest(github_json, [github_entry("same.py")])

    with pytest.raises(ValueError, match="CSV integrity check"):
        build_comparison(
            replit_csv,
            github_json,
            expected_replit_sha256="0" * 64,
        )

    result = build_comparison(
        replit_csv,
        github_json,
        replit_head="c" * 40,
        expected_replit_sha256=digest,
    )
    assert result["replit"]["head_sha"] == "c" * 40
    assert result["replit"]["source_file_sha256"] == digest
