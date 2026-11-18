import hashlib
import json
import os
import subprocess

from tools.source_manifest import build_manifest


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def init_repo(root):
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "Manifest Test")
    git(root, "config", "user.email", "manifest-test@example.invalid")
    git(root, "config", "core.filemode", "true")
    return root


def commit_all(root):
    git(root, "add", "-A")
    git(root, "commit", "-m", "fixture")


def by_path(manifest):
    return {entry["path"]: entry for entry in manifest["entries"]}


def test_manifest_hashes_committed_blobs_and_is_deterministic(tmp_path):
    root = init_repo(tmp_path / "repo")
    source = root / "src" / "main.py"
    source.parent.mkdir()
    source.write_bytes(b"print('atlas')\n")
    source.chmod(0o755)
    commit_all(root)

    first = build_manifest(root)
    second = build_manifest(root)
    entry = by_path(first)["src/main.py"]

    assert first == second
    assert first["complete"] is True
    assert first["clean_tracked_worktree"] is True
    assert first["tracked_entry_count"] == 1
    assert entry["mode"] == "100755"
    assert entry["content_kind"] == "file"
    assert entry["size_bytes"] == len(b"print('atlas')\n")
    assert entry["sha256"] == hashlib.sha256(b"print('atlas')\n").hexdigest()
    assert len(first["manifest_sha256"]) == 64


def test_manifest_hashes_symlink_target_without_following_it(tmp_path):
    root = init_repo(tmp_path / "repo")
    (root / "target.txt").write_text("target content", encoding="utf-8")
    os.symlink("target.txt", root / "shortcut")
    commit_all(root)

    entry = by_path(build_manifest(root))["shortcut"]

    assert entry["mode"] == "120000"
    assert entry["content_kind"] == "symlink_target"
    assert entry["size_bytes"] == len(b"target.txt")
    assert entry["sha256"] == hashlib.sha256(b"target.txt").hexdigest()


def test_manifest_lists_but_never_hashes_sensitive_or_generated_paths(tmp_path):
    root = init_repo(tmp_path / "repo")
    secret_value = "manifest-fixture-secret-do-not-print"
    (root / ".env").write_text(secret_value, encoding="utf-8")
    (root / ".env.example").write_text("ATLAS_MODE=off\n", encoding="utf-8")
    (root / "keys").mkdir()
    (root / "keys" / "private.pem").write_text(secret_value, encoding="utf-8")
    (root / "dist").mkdir()
    (root / "dist" / "bundle.js").write_text("generated", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("pass\n", encoding="utf-8")
    commit_all(root)

    manifest = build_manifest(root)
    entries = by_path(manifest)
    rendered = json.dumps(manifest)

    assert entries[".env"]["sha256"] is None
    assert entries[".env"]["excluded_reason"] == "environment_file"
    assert entries["keys/private.pem"]["sha256"] is None
    assert entries["keys/private.pem"]["excluded_reason"] == "credential_or_private_key"
    assert entries["dist/bundle.js"]["sha256"] is None
    assert entries["dist/bundle.js"]["excluded_reason"] == "generated_directory"
    assert entries[".env.example"]["sha256"] == hashlib.sha256(
        b"ATLAS_MODE=off\n"
    ).hexdigest()
    assert entries["src/app.py"]["sha256"] == hashlib.sha256(b"pass\n").hexdigest()
    assert manifest["excluded_entry_count"] == 3
    assert secret_value not in rendered


def test_manifest_describes_head_snapshot_and_reports_dirty_worktree(tmp_path):
    root = init_repo(tmp_path / "repo")
    source = root / "tracked.txt"
    source.write_text("committed version", encoding="utf-8")
    commit_all(root)

    source.write_text("uncommitted version", encoding="utf-8")
    (root / "untracked.txt").write_text("not part of HEAD", encoding="utf-8")
    manifest = build_manifest(root)
    entry = by_path(manifest)["tracked.txt"]

    assert manifest["clean_tracked_worktree"] is False
    assert manifest["untracked_file_count"] == 1
    assert manifest["tracked_entry_count"] == 1
    assert entry["sha256"] == hashlib.sha256(b"committed version").hexdigest()
    assert "untracked.txt" not in by_path(manifest)


def test_manifest_marks_git_lfs_pointer_without_fetching_payload(tmp_path):
    root = init_repo(tmp_path / "repo")
    pointer = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:" + b"a" * 64 + b"\nsize 4096\n"
    )
    (root / "large-model.bin").write_bytes(pointer)
    commit_all(root)

    entry = by_path(build_manifest(root))["large-model.bin"]

    assert entry["content_kind"] == "git_lfs_pointer"
    assert entry["size_bytes"] == len(pointer)
    assert entry["sha256"] == hashlib.sha256(pointer).hexdigest()
