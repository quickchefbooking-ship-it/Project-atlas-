"""Bounded, public-metadata research adapters for GitHub and Hugging Face.

These adapters use fixed HTTPS API hosts, make GET requests only, impose response
limits/timeouts, and return normalized records for approval-gated ingestion.
They do not fetch arbitrary URLs, access private resources, or store credentials.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
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


LEGISLATION_TYPES = {"ukpga", "uksi", "asp", "anaw", "nia", "nisr", "ukla"}
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _get_xml_text(url: str) -> str:
    """GET XML/text from the fixed official legislation host with strict bounds."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "www.legislation.gov.uk":
        raise PublicSourceError("Legislation requests must use the official HTTPS host.")
    request = Request(url, headers={"Accept": "application/atom+xml, application/xml, text/xml", "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        if exc.code == 404:
            raise PublicSourceError("The legislation resource was not found.") from exc
        if exc.code == 429:
            raise PublicSourceError("The legislation service rate limit was reached.") from exc
        raise PublicSourceError(f"Legislation service returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise PublicSourceError("The official legislation service could not be reached.") from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise PublicSourceError("Legislation response exceeded the 1 MB safety limit.")
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PublicSourceError("Legislation service returned non-UTF-8 content.") from exc


def search_uk_legislation(query: str, legislation_type: str = "ukpga", limit: int = 5) -> list[SourceDocument]:
    """Search official legislation.gov.uk Atom feeds and stage current XML text."""
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 120:
        raise PublicSourceError("Legislation search must contain 2 to 120 characters.")
    if legislation_type not in LEGISLATION_TYPES:
        raise PublicSourceError("Unsupported UK legislation type.")
    if not isinstance(limit, int) or limit < 1 or limit > 5:
        raise PublicSourceError("Legislation result limit must be between 1 and 5.")

    params = urlencode({"type": legislation_type, "title": query.strip(), "results-count": str(limit), "sort": "modified"})
    feed_url = f"https://www.legislation.gov.uk/search/data.feed?{params}"
    feed_text = _get_xml_text(feed_url)
    try:
        root = ET.fromstring(feed_text)
    except ET.ParseError as exc:
        raise PublicSourceError("Official legislation search returned invalid Atom XML.") from exc

    entries = root.findall("atom:entry", ATOM_NS)
    retrieved = _retrieved_at()
    documents: list[SourceDocument] = []
    for entry in entries[:limit]:
        title_node = entry.find("atom:title", ATOM_NS)
        title = " ".join("".join(title_node.itertext()).split()) if title_node is not None else ""
        links = entry.findall("atom:link", ATOM_NS)
        href = next((item.get("href") for item in links if item.get("href") and item.get("rel", "alternate") == "alternate"), None)
        if not title or not href:
            continue
        parsed = urlparse(href)
        if parsed.scheme != "https" or parsed.hostname != "www.legislation.gov.uk":
            continue
        canonical_uri = f"https://www.legislation.gov.uk{parsed.path.rstrip('/')}"
        xml_url = canonical_uri + "/data.xml"
        xml_text = _get_xml_text(xml_url)
        try:
            legal_root = ET.fromstring(xml_text)
        except ET.ParseError:
            continue
        body_text = " ".join(" ".join(legal_root.itertext()).split())
        if not body_text:
            continue
        content = f"Official UK legislation text and metadata\nTitle: {title}\nSource: {canonical_uri}\n\n{body_text}"
        if len(content) > 900_000:
            content = content[:900_000] + "\n[Truncated at the adapter safety limit.]"
        documents.append(SourceDocument(
            title=title,
            uri=canonical_uri,
            content=content,
            metadata={
                "provider": "legislation.gov.uk",
                "publisher": "The National Archives",
                "resource_type": legislation_type,
                "retrieved_at": retrieved,
                "record_kind": "official_legislation_text",
                "content_format": "XML extracted text",
                "licence": "Open Government Licence",
            },
        ))
    return documents


def search_crossref_works(query: str, limit: int = 5) -> list[SourceDocument]:
    """Search Crossref's public scholarly metadata API; abstracts only when supplied."""
    if not isinstance(query, str) or not 3 <= len(query.strip()) <= 160:
        raise PublicSourceError("Scholarly search must contain 3 to 160 characters.")
    if not isinstance(limit, int) or limit < 1 or limit > 5:
        raise PublicSourceError("Scholarly result limit must be between 1 and 5.")
    params = urlencode({
        "query.bibliographic": query.strip(),
        "rows": str(limit),
        "select": "DOI,title,author,publisher,published-print,published-online,type,URL,abstract,license,is-referenced-by-count,created",
    })
    payload = _get_json(f"https://api.crossref.org/works?{params}")
    message = payload.get("message")
    items = message.get("items", []) if isinstance(message, dict) else []
    if not isinstance(items, list):
        raise PublicSourceError("Crossref returned an unexpected works response.")
    retrieved = _retrieved_at()
    documents: list[SourceDocument] = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        doi = item.get("DOI")
        if not isinstance(doi, str) or not re.fullmatch(r"10\.\d{4,9}/\S+", doi):
            continue
        title_values = item.get("title")
        title = " ".join(title_values[0].split()) if isinstance(title_values, list) and title_values and isinstance(title_values[0], str) else ""
        if not title:
            title = f"Crossref work {doi}"
        authors = []
        for author in item.get("author", [])[:30] if isinstance(item.get("author"), list) else []:
            if isinstance(author, dict):
                name = " ".join(part for part in [author.get("given"), author.get("family")] if isinstance(part, str) and part.strip())
                if name:
                    authors.append(name)
        fields = {
            "doi": doi,
            "authors": authors,
            "publisher": item.get("publisher"),
            "type": item.get("type"),
            "published_print": item.get("published-print"),
            "published_online": item.get("published-online"),
            "citation_count": item.get("is-referenced-by-count"),
            "created": item.get("created"),
            "license": item.get("license", []),
            "abstract": item.get("abstract"),
            "landing_page": item.get("URL"),
        }
        content = "Crossref scholarly metadata\n" + json.dumps(fields, ensure_ascii=False, indent=2, sort_keys=True)
        documents.append(SourceDocument(
            title=title,
            uri=f"https://doi.org/{doi}",
            content=content,
            metadata={
                "provider": "crossref",
                "resource_type": "scholarly_work",
                "doi": doi,
                "publisher": item.get("publisher"),
                "retrieved_at": retrieved,
                "record_kind": "bibliographic_metadata",
                "abstract_included": bool(item.get("abstract")),
                "full_text_not_fetched": True,
            },
        ))
    return documents
