"""Deterministic bibliographic work identity and conservative duplicate grouping.

Identifiers are evidence for a possible same-work relationship, not proof of
scientific independence. Conflicting DOI values prevent a provider-ID or URL
alias from silently merging records.
"""
from __future__ import annotations

import re
from collections import defaultdict
from urllib.parse import urlsplit, urlunsplit

DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
ALLOWED_PROVIDER_IDS = {
    "crossref", "pubmed", "pmid", "openalex", "arxiv", "semantic_scholar",
}
MAX_IDENTIFIER_CHARS = 512


def normalize_doi(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_IDENTIFIER_CHARS:
        raise ValueError("DOI identifier is invalid.")
    candidate = value.strip()
    lowered = candidate.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if lowered.startswith(prefix):
            candidate = candidate[len(prefix):].strip()
            break
    if not DOI_PATTERN.fullmatch(candidate):
        raise ValueError("DOI identifier is invalid.")
    return candidate.lower()


def normalize_canonical_uri(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ValueError("Canonical source URI is invalid.")
    parsed = urlsplit(value.strip())
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Canonical source URI is invalid.") from exc
    scheme = parsed.scheme.lower()
    expected_port = 80 if scheme == "http" else 443
    if (
        scheme not in {"http", "https"}
        or not parsed.hostname or parsed.username is not None
        or parsed.password is not None or port not in (None, expected_port)
        or parsed.fragment
    ):
        raise ValueError("Canonical source URI must be HTTP(S), without credentials, fragments or alternate ports.")
    host = parsed.hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    # Query parameters are preserved: stripping them can conflate distinct
    # resources or versions. Fragments are discarded only by rejection.
    return urlunsplit((scheme, host, path, parsed.query, ""))


def normalize_provider_identifiers(values: dict | None) -> dict[str, str]:
    if values is None:
        return {}
    if not isinstance(values, dict) or len(values) > len(ALLOWED_PROVIDER_IDS):
        raise ValueError("Provider identifiers must be a bounded object.")
    normalized = {}
    for provider, identifier in values.items():
        if provider not in ALLOWED_PROVIDER_IDS:
            raise ValueError("Provider identifier namespace is not supported.")
        if (
            not isinstance(identifier, str) or not identifier.strip()
            or len(identifier) > MAX_IDENTIFIER_CHARS
        ):
            raise ValueError("Provider identifier value is invalid.")
        normalized[provider] = identifier.strip().lower()
    return normalized


def detect_duplicate_work_groups(records: list[dict]) -> dict:
    """Return conservative duplicate groups, aliases and identifier conflicts."""
    if not isinstance(records, list):
        raise ValueError("Source records must be a list.")
    normalized = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError("Source record must be an object.")
        doi = normalize_doi(record.get("doi"))
        uri = normalize_canonical_uri(record.get("uri"))
        providers = normalize_provider_identifiers(record.get("identifiers"))
        keys = []
        if doi:
            keys.append("doi:" + doi)
        keys.append("uri:" + uri)
        keys.extend(f"id:{provider}:{value}" for provider, value in sorted(providers.items()))
        normalized.append({"index": index, "doi": doi, "keys": keys})

    parent = list(range(len(normalized)))

    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left, right):
        a, b = find(left), find(right)
        if a != b:
            parent[max(a, b)] = min(a, b)

    key_owners = defaultdict(list)
    for item in normalized:
        for key in item["keys"]:
            key_owners[key].append(item["index"])

    conflicts = []
    for key, owners in sorted(key_owners.items()):
        if len(owners) < 2:
            continue
        for offset, left in enumerate(owners):
            for right in owners[offset + 1:]:
                left_doi, right_doi = normalized[left]["doi"], normalized[right]["doi"]
                if left_doi and right_doi and left_doi != right_doi:
                    conflicts.append({
                        "identifier_key": key,
                        "source_indices": [left, right],
                        "doi_values": [left_doi, right_doi],
                        "status": "conflicting_identifiers_not_merged",
                    })
                    continue
                union(left, right)

    groups = defaultdict(list)
    for item in normalized:
        groups[find(item["index"])].append(item)
    duplicate_groups = []
    for members in groups.values():
        if len(members) < 2:
            continue
        aliases = sorted({key for member in members for key in member["keys"]})
        duplicate_groups.append({
            "source_indices": sorted(member["index"] for member in members),
            "identifier_aliases": aliases,
            "status": "possible_same_work",
            "notice": "Shared bibliographic identifiers group these records; they are not independent corroboration.",
        })

    return {
        "duplicate_groups": sorted(duplicate_groups, key=lambda group: group["source_indices"]),
        "identifier_conflicts": conflicts,
        "limitations": [
            "Identifier matching is deterministic record deduplication, not proof that two records are the same scientific work.",
            "Missing or conflicting identifiers can prevent a match; do not infer independence from separate groups.",
            "No scientific independence, study quality, claim support or factual truth assessment is performed.",
        ],
    }
