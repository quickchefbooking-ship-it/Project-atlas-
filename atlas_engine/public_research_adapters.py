"""Bounded, public-metadata research adapters for GitHub and Hugging Face.

These adapters use fixed HTTPS API hosts, make GET requests only, impose response
limits/timeouts, and return normalized records for approval-gated ingestion.
They do not fetch arbitrary URLs, access private resources, or store credentials.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .source_adapters import SourceDocument

MAX_RESPONSE_BYTES = 1_000_000
REQUEST_TIMEOUT_SECONDS = 8
USER_AGENT = "AtlasOnePro-SourceDivision/0.1 (public metadata; read-only)"


class PublicSourceError(ValueError):
    """A public provider request failed or returned unusable data."""


def _get_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/vnd.github+json, application/json", "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        if exc.code == 404:
            raise PublicSourceError("Public resource was not found.") from exc
        if exc.code == 403 or exc.code == 429:
            raise PublicSourceError("Provider rate limit or access policy prevented this request.") from exc
        raise PublicSourceError(f"Provider returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise PublicSourceError("Provider could not be reached; try again later.") from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise PublicSourceError("Provider response exceeded the 1 MB safety limit.")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicSourceError("Provider returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise PublicSourceError("Provider returned an unexpected response.")
    return payload


def _retrieved_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_github_repository(identifier: str) -> SourceDocument:
    """Fetch public GitHub repository metadata (not source files or private data)."""
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", identifier):
        raise PublicSourceError("GitHub identifier must be an owner/repository pair.")
    payload = _get_json(f"https://api.github.com/repos/{identifier}")
    canonical_url = payload.get("html_url")
    if not isinstance(canonical_url, str) or not canonical_url.startswith("https://github.com/"):
        raise PublicSourceError("GitHub response did not contain a valid canonical repository URL.")
    fields = {
        "full_name": payload.get("full_name"),
        "description": payload.get("description"),
        "language": payload.get("language"),
        "topics": payload.get("topics", []),
        "license": (payload.get("license") or {}).get("spdx_id") if isinstance(payload.get("license"), dict) else None,
        "default_branch": payload.get("default_branch"),
        "stars": payload.get("stargazers_count"),
        "forks": payload.get("forks_count"),
        "open_issues": payload.get("open_issues_count"),
        "updated_at": payload.get("updated_at"),
    }
    retrieved = _retrieved_at()
    content = "Public GitHub repository metadata\n" + json.dumps(fields, ensure_ascii=False, indent=2, sort_keys=True)
    return SourceDocument(
        title=f"GitHub repository: {payload.get('full_name') or identifier}",
        uri=canonical_url,
        content=content,
        metadata={"provider": "github", "resource_type": "repository", "identifier": identifier, "retrieved_at": retrieved, "record_kind": "public_metadata"},
    )


def fetch_huggingface_resource(identifier: str, resource_type: str = "model") -> SourceDocument:
    """Fetch public Hugging Face model or dataset metadata, not model weights."""
    if resource_type not in {"model", "dataset"}:
        raise PublicSourceError("Hugging Face resource_type must be model or dataset.")
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}(?:/[A-Za-z0-9_.-]{1,100})?", identifier):
        raise PublicSourceError("Hugging Face identifier must be a public resource name such as organisation/model.")
    endpoint = "models" if resource_type == "model" else "datasets"
    payload = _get_json(f"https://huggingface.co/api/{endpoint}/{identifier}")
    canonical_url = payload.get("url")
    if not isinstance(canonical_url, str) or not canonical_url.startswith("https://huggingface.co/"):
        canonical_url = f"https://huggingface.co/{identifier}" if resource_type == "model" else f"https://huggingface.co/datasets/{identifier}"
    fields = {
        "id": payload.get("id"),
        "author": payload.get("author"),
        "pipeline_tag": payload.get("pipeline_tag"),
        "library_name": payload.get("library_name"),
        "tags": payload.get("tags", []),
        "license": payload.get("license"),
        "downloads": payload.get("downloads"),
        "likes": payload.get("likes"),
        "last_modified": payload.get("lastModified"),
        "private": payload.get("private"),
        "gated": payload.get("gated"),
    }
    retrieved = _retrieved_at()
    content = f"Public Hugging Face {resource_type} metadata\n" + json.dumps(fields, ensure_ascii=False, indent=2, sort_keys=True)
    return SourceDocument(
        title=f"Hugging Face {resource_type}: {payload.get('id') or identifier}",
        uri=canonical_url,
        content=content,
        metadata={"provider": "huggingface", "resource_type": resource_type, "identifier": identifier, "retrieved_at": retrieved, "record_kind": "public_metadata"},
    )
