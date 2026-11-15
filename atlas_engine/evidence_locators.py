"""Deterministic locator resolution for approved HTML source snapshots.

No URL is fetched and no browser or script is executed. Resolution is performed
only against the immutable source text already stored by Atlas.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from . import storage

MAX_HTML_CHARS = 1_000_000
MAX_EXCERPT_CHARS = 2_000
_BLOCK_TAGS = {
    "address", "blockquote", "caption", "dd", "dt", "figcaption",
    "h1", "h2", "h3", "h4", "h5", "h6", "li", "p", "pre", "td", "th",
}
_IGNORED_TAGS = {"script", "style", "noscript", "svg", "template"}
_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


def _normalise_text(value: str) -> str:
    return re.sub(r"\\s+", " ", value).strip()


@dataclass
class _Frame:
    tag: str
    path: str
    block_index: int | None = None
    ignored: bool = False
    child_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))


class _BlockExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[_Frame] = []
        self.blocks: list[dict[str, str]] = []
        self.root_counts: dict[str, int] = defaultdict(int)
        self.ignore_depth = 0

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        parent = self.stack[-1] if self.stack else None
        counts = parent.child_counts if parent else self.root_counts
        counts[tag] += 1
        parent_path = parent.path if parent else "html"
        path = f"{parent_path}/{tag}[{counts[tag]}]"
        ignored = tag in _IGNORED_TAGS or self.ignore_depth > 0
        block_index = None
        if ignored:
            self.ignore_depth += 1
        elif tag in _BLOCK_TAGS:
            block_index = len(self.blocks)
            self.blocks.append({"locator": path, "text": ""})
        frame = _Frame(tag, path, block_index, ignored)
        if tag not in _VOID_TAGS:
            self.stack.append(frame)
        elif tag == "br" and not self.ignore_depth and self._active_block() is not None:
            self.blocks[self._active_block()]["text"] += " "

    def handle_endtag(self, tag):
        tag = tag.lower()
        for index in range(len(self.stack) - 1, -1, -1):
            frame = self.stack[index]
            if frame.tag == tag:
                removed = self.stack[index:]
                del self.stack[index:]
                self.ignore_depth = max(0, self.ignore_depth - sum(1 for item in removed if item.ignored))
                return

    def _active_block(self) -> int | None:
        for frame in reversed(self.stack):
            if frame.ignored:
                return None
            if frame.block_index is not None:
                return frame.block_index
        return None

    def handle_data(self, data):
        if self.ignore_depth:
            return
        index = self._active_block()
        if index is not None:
            self.blocks[index]["text"] += data

    def handle_entityref(self, name):
        self.handle_data(f"&{name};")

    def handle_charref(self, name):
        self.handle_data(f"&#{name};")


def extract_html_blocks(source_text: str) -> list[dict[str, str]]:
    """Extract semantic HTML blocks with deterministic structural locators."""
    if not isinstance(source_text, str) or not source_text or len(source_text) > MAX_HTML_CHARS:
        raise ValueError("HTML source must be non-empty text within the 1 MB character limit.")
    parser = _BlockExtractor()
    try:
        parser.feed(source_text)
        parser.close()
    except Exception as exc:
        raise ValueError("HTML source could not be parsed.") from exc
    return [
        {"locator": item["locator"], "text": _normalise_text(item["text"])}
        for item in parser.blocks if _normalise_text(item["text"])
    ]


def resolve_approved_html_excerpt(
    *, source_document_id: str, excerpt: str,
) -> dict[str, Any]:
    """Resolve an exact excerpt to a semantic block in an approved HTML snapshot."""
    if not isinstance(source_document_id, str) or not source_document_id.strip():
        raise ValueError("A source_document_id is required.")
    if not isinstance(excerpt, str) or not excerpt.strip() or len(excerpt) > MAX_EXCERPT_CHARS:
        raise ValueError("Excerpt must be non-empty text of at most 2,000 characters.")
    document = storage.get_source_document(source_document_id)
    if document is None:
        raise ValueError("Approved HTML source document was not found.")
    if document.get("state") != "approved" or document.get("trust_level") not in {"reviewed", "authoritative"}:
        raise ValueError("Only an approved, reviewed HTML source can be resolved.")
    try:
        metadata = json.loads(document.get("metadata_json") or "{}")
    except (TypeError, ValueError) as exc:
        raise ValueError("Stored source metadata is invalid.") from exc
    if not isinstance(metadata, dict) or metadata.get("content_type") != "text/html":
        raise ValueError("Source document is not registered as text/html.")
    source_text = document.get("content")
    stored_digest = document.get("content_sha256")
    if not isinstance(source_text, str) or not isinstance(stored_digest, str):
        raise ValueError("Stored HTML source snapshot is incomplete.")
    actual_digest = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    if actual_digest != stored_digest:
        raise ValueError("Stored HTML source snapshot digest does not match its content.")

    quote = _normalise_text(excerpt)
    matches = [
        block for block in extract_html_blocks(source_text)
        if quote in block["text"]
    ]
    if len(matches) == 0:
        status = "excerpt_not_found"
        locator = None
    elif len(matches) == 1:
        status = "exact_excerpt_found"
        locator = matches[0]["locator"]
    else:
        status = "ambiguous_excerpt"
        locator = None

    return {
        "schema_version": 1,
        "source_document_id": document["id"],
        "source_title": document["title"],
        "source_uri": document["uri"],
        "source_state": document["state"],
        "source_trust_level": document["trust_level"],
        "source_content_sha256": stored_digest,
        "excerpt_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        "locator_status": status,
        "locator": locator,
        "matching_block_count": len(matches),
        "locator_method": "semantic_html_block_exact_text_v1",
        "reviewer_identity_verified": False,
        "limitations": [
            "The locator is derived from the stored HTML snapshot, not a live website.",
            "The structural path is deterministic for this snapshot but may change in a later source version.",
            "Exact text location does not establish that the excerpt supports a claim.",
            "This resolver does not fetch URLs, execute scripts, render CSS, or resolve PDF page coordinates.",
        ],
    }
