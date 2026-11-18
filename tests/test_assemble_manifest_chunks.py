import csv
import hashlib
from pathlib import Path

import pytest

from tools.assemble_manifest_chunks import CSV_COLUMNS, assemble_chunks


def row(path, *, mode="100644", size=4, digest="a" * 64):
    return {
        "path": path,
        "mode": mode,
        "bytes": str(size),
        "sha256": digest,
        "status": "hashed",
        "exclusion_reason": "",
    }


def write_chunk(directory, number, rows):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"chunk-{number:03d}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_assembles_bounded_chunks_and_checks_canonical_digest(tmp_path):
    chunks = tmp_path / "chunks"
    write_chunk(chunks, 1, [row("a.py"), row("b.py")])
    write_chunk(chunks, 2, [row("c.py")])

    rendered, summary = assemble_chunks(chunks, expected_row_count=3, max_rows_per_chunk=2)
    assert summary["chunk_count"] == 2
    assert summary["row_count"] == 3
    assert summary["byte_length"] == len(rendered)
    assert summary["sha256"] == hashlib.sha256(rendered).hexdigest()
    assert rendered.decode("utf-8").splitlines()[0] == ",".join(CSV_COLUMNS)

    rendered_again, summary_again = assemble_chunks(
        chunks,
        expected_row_count=3,
        max_rows_per_chunk=2,
        expected_sha256=summary["sha256"],
    )
    assert rendered_again == rendered
    assert summary_again == summary


def test_rejects_missing_chunk_sequence(tmp_path):
    chunks = tmp_path / "chunks"
    write_chunk(chunks, 1, [row("a.py")])
    write_chunk(chunks, 3, [row("b.py")])
    with pytest.raises(ValueError, match="sequence"):
        assemble_chunks(chunks, expected_row_count=2)


def test_rejects_oversized_chunk(tmp_path):
    chunks = tmp_path / "chunks"
    write_chunk(chunks, 1, [row("a.py"), row("b.py"), row("c.py")])
    with pytest.raises(ValueError, match="row limit"):
        assemble_chunks(chunks, expected_row_count=3, max_rows_per_chunk=2)


def test_rejects_unsorted_and_duplicate_paths(tmp_path):
    chunks = tmp_path / "chunks"
    write_chunk(chunks, 1, [row("b.py"), row("a.py")])
    with pytest.raises(ValueError, match="sorted"):
        assemble_chunks(chunks, expected_row_count=2)

    chunks = tmp_path / "duplicate"
    write_chunk(chunks, 1, [row("a.py")])
    write_chunk(chunks, 2, [row("a.py")])
    with pytest.raises(ValueError, match="duplicate"):
        assemble_chunks(chunks, expected_row_count=2)


@pytest.mark.parametrize(
    "unsafe_path",
    ["/absolute.py", "../outside.py", "a/../outside.py", "a//b.py", "./file.py", "a/./b.py", "a/"],
)
def test_rejects_non_repository_relative_paths(tmp_path, unsafe_path):
    chunks = tmp_path / "chunks"
    write_chunk(chunks, 1, [row(unsafe_path)])
    with pytest.raises(ValueError, match="repository-relative"):
        assemble_chunks(chunks, expected_row_count=1)


def test_rejects_symlinked_chunk_file(tmp_path):
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    source = write_chunk(tmp_path / "source", 1, [row("a.py")])
    (chunks / "chunk-001.csv").symlink_to(source)

    with pytest.raises(ValueError, match="regular chunk CSV"):
        assemble_chunks(chunks, expected_row_count=1)


def test_rejects_symlinked_chunk_directory(tmp_path):
    source_dir = tmp_path / "source"
    write_chunk(source_dir, 1, [row("a.py")])
    chunks = tmp_path / "chunks"
    chunks.symlink_to(source_dir, target_is_directory=True)

    with pytest.raises(ValueError, match="real directory"):
        assemble_chunks(chunks, expected_row_count=1)


def test_rejects_excluded_rows_in_sanitized_transfer(tmp_path):
    chunks = tmp_path / "chunks"
    excluded = row(".env")
    excluded["sha256"] = ""
    excluded["status"] = "excluded"
    excluded["exclusion_reason"] = "environment_file"
    write_chunk(chunks, 1, [excluded])
    with pytest.raises(ValueError, match="hashed-only"):
        assemble_chunks(chunks, expected_row_count=1)


def test_rejects_row_count_and_digest_mismatch(tmp_path):
    chunks = tmp_path / "chunks"
    write_chunk(chunks, 1, [row("a.py")])
    with pytest.raises(ValueError, match="row count"):
        assemble_chunks(chunks, expected_row_count=2)
    with pytest.raises(ValueError, match="SHA-256"):
        assemble_chunks(chunks, expected_row_count=1, expected_sha256="0" * 64)


def test_rejects_invalid_header_and_empty_chunk(tmp_path):
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    (chunks / "chunk-001.csv").write_text("path,mode\\na.py,100644\\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        assemble_chunks(chunks, expected_row_count=1)

    chunks = tmp_path / "empty"
    write_chunk(chunks, 1, [])
    with pytest.raises(ValueError, match="empty"):
        assemble_chunks(chunks, expected_row_count=1)


def test_rejects_invalid_hash_and_mode(tmp_path):
    chunks = tmp_path / "chunks"
    write_chunk(chunks, 1, [row("a.py", digest="invalid")])
    with pytest.raises(ValueError, match="SHA-256"):
        assemble_chunks(chunks, expected_row_count=1)

    chunks = tmp_path / "bad-mode"
    write_chunk(chunks, 1, [row("a.py", mode="000000")])
    with pytest.raises(ValueError, match="Git mode"):
        assemble_chunks(chunks, expected_row_count=1)
