"""Assemble bounded CSV manifest chunks with strict integrity checks.

This accepts a sanitized hashed-only Replit metadata export. Excluded rows are
not transferred; their count is recorded separately in the reconciliation notes.
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

CSV_COLUMNS = ["path", "mode", "bytes", "sha256", "status", "exclusion_reason"]
CHUNK_RE = re.compile(r"chunk-(\d{3,})\.csv$")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
GIT_MODES = {"100644", "100755", "120000"}


def _validate_row(row: dict[str, Any], source: str) -> dict[str, str]:
    if None in row or any(value is None for value in row.values()):
        raise ValueError(f"{source} has missing or extra CSV columns.")
    path = row.get("path")
    if not isinstance(path, str) or not path:
        raise ValueError(f"{source} has an empty or invalid path.")
    # Preserve the exact path string; reject only paths that cannot safely
    # represent a repository-relative Git tree entry.
    if "\x00" in path or path.startswith("/") or any(
        part in {"", ".", ".."} for part in path.split("/")
    ):
        raise ValueError(f"{source} has a path that is not repository-relative.")
    mode = row.get("mode")
    if mode not in GIT_MODES:
        raise ValueError(f"{source} has an unsupported Git mode.")
    raw_size = row.get("bytes")
    if not isinstance(raw_size, str) or not raw_size.isdigit():
        raise ValueError(f"{source} has an invalid byte count.")
    if row.get("status") != "hashed" or row.get("exclusion_reason") != "":
        raise ValueError(f"{source} is not a sanitized hashed-only row.")
    digest = row.get("sha256")
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        raise ValueError(f"{source} has an invalid SHA-256 digest.")
    return {
        "path": path,
        "mode": mode,
        "bytes": raw_size,
        "sha256": digest,
        "status": "hashed",
        "exclusion_reason": "",
    }


def assemble_chunks(
    chunks_dir: Path,
    *,
    expected_row_count: int,
    max_rows_per_chunk: int = 50,
    expected_sha256: str | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Return canonical CSV bytes and summary, without writing any files."""
    if expected_row_count < 1 or max_rows_per_chunk < 1:
        raise ValueError("Expected row count and chunk limit must be positive.")
    if expected_sha256 is not None and SHA256_RE.fullmatch(expected_sha256) is None:
        raise ValueError("Expected CSV digest is invalid.")
    if chunks_dir.is_symlink() or not chunks_dir.is_dir():
        raise ValueError("Chunk directory must be a real directory.")

    files = sorted(chunks_dir.iterdir(), key=lambda item: item.name)
    if not files:
        raise ValueError("No chunk files were found.")

    numbered: list[tuple[int, Path]] = []
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise ValueError("Chunk directory may contain only regular chunk CSV files.")
        match = CHUNK_RE.fullmatch(path.name)
        if match is None:
            raise ValueError("Chunk filename must be chunk-NNN.csv.")
        numbered.append((int(match.group(1)), path))

    if [number for number, _ in numbered] != list(range(1, len(numbered) + 1)):
        raise ValueError("Chunk sequence must start at 1 and contain no gaps.")

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    previous_path: str | None = None
    for number, path in numbered:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != CSV_COLUMNS:
                raise ValueError(f"Chunk {number} header does not match the schema.")
            chunk_rows: list[dict[str, str]] = []
            for row_index, row in enumerate(reader, start=2):
                validated = _validate_row(row, f"Chunk {number} row {row_index}")
                path_value = validated["path"]
                if path_value in seen:
                    raise ValueError("Manifest chunks contain a duplicate path.")
                if previous_path is not None and path_value <= previous_path:
                    raise ValueError("Manifest paths must be globally sorted and unique.")
                seen.add(path_value)
                previous_path = path_value
                chunk_rows.append(validated)
            if not chunk_rows:
                raise ValueError(f"Chunk {number} is empty.")
            if len(chunk_rows) > max_rows_per_chunk:
                raise ValueError(f"Chunk {number} exceeds the row limit.")
            rows.extend(chunk_rows)

    if len(rows) != expected_row_count:
        raise ValueError("Assembled row count does not match the expected count.")

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    rendered = stream.getvalue().encode("utf-8")
    digest = hashlib.sha256(rendered).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError("Assembled CSV SHA-256 does not match the expected digest.")

    return rendered, {
        "chunk_count": len(numbered),
        "row_count": len(rows),
        "byte_length": len(rendered),
        "sha256": digest,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and assemble bounded manifest CSV chunks.")
    parser.add_argument("--chunks-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-row-count", type=int, required=True)
    parser.add_argument("--max-rows-per-chunk", type=int, default=50)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args(argv)

    try:
        rendered, summary = assemble_chunks(
            args.chunks_dir,
            expected_row_count=args.expected_row_count,
            max_rows_per_chunk=args.max_rows_per_chunk,
            expected_sha256=args.expected_sha256,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(rendered)
    except (OSError, ValueError) as exc:
        print(f"manifest chunk assembly failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
