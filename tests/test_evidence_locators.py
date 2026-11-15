import pytest

from atlas_engine import storage
from atlas_engine.evidence_locators import (
    extract_html_blocks,
    resolve_approved_html_excerpt,
)
from atlas_engine.source_division import ingest_document, register_source, review_document


HTML = """<!doctype html><html><body>
<h1>Research findings</h1>
<p id="intro">The study reported a measurable association in the sample.</p>
<div><p>Limitations were described by the authors.</p></div>
<script>const hidden = "The study reported a measurable association in the sample.";</script>
</body></html>"""


def _approved_html(monkeypatch, tmp_path, html=HTML):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "html-locators.sqlite"))
    storage.init_db()
    register_source("html-research", "HTML Research", "manual_import")
    document = ingest_document(
        "html-research",
        "Research findings",
        "https://example.org/research",
        html,
        metadata={"content_type": "text/html", "publisher": "Example Institute"},
    )
    review_document(document["id"], "approved", "reviewer-label")
    return document


def test_html_excerpt_resolves_to_stable_semantic_block(monkeypatch, tmp_path):
    document = _approved_html(monkeypatch, tmp_path)

    result = resolve_approved_html_excerpt(
        source_document_id=document["id"],
        excerpt="The study reported a measurable association in the sample.",
    )

    assert result["locator_status"] == "exact_excerpt_found"
    assert result["locator"] == "html/html[1]/body[1]/p[1]"
    assert result["source_content_sha256"] == document["content_sha256"]
    assert result["locator_method"] == "semantic_html_block_exact_text_v1"
    assert result["reviewer_identity_verified"] is False


def test_html_extractor_ignores_script_and_style_content():
    blocks = extract_html_blocks(
        "<html><body><p>Visible source text.</p>"
        "<script>Visible source text.</script>"
        "<style>.x { content: 'Visible source text'; }</style>"
        "</body></html>"
    )
    assert [item["text"] for item in blocks] == ["Visible source text."]


def test_duplicate_excerpt_in_multiple_blocks_is_ambiguous(monkeypatch, tmp_path):
    html = "<html><body><p>Repeated phrase.</p><p>Repeated phrase.</p></body></html>"
    document = _approved_html(monkeypatch, tmp_path, html)

    result = resolve_approved_html_excerpt(
        source_document_id=document["id"], excerpt="Repeated phrase."
    )

    assert result["locator_status"] == "ambiguous_excerpt"
    assert result["locator"] is None
    assert result["matching_block_count"] == 2


def test_missing_excerpt_returns_not_found(monkeypatch, tmp_path):
    document = _approved_html(monkeypatch, tmp_path)
    result = resolve_approved_html_excerpt(
        source_document_id=document["id"], excerpt="Text not in this source."
    )
    assert result["locator_status"] == "excerpt_not_found"
    assert result["locator"] is None


def test_pending_html_source_is_not_resolvable(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "pending.sqlite"))
    storage.init_db()
    register_source("html-research", "HTML Research", "manual_import")
    document = ingest_document(
        "html-research", "Pending", "https://example.org/pending",
        "<p>Pending content.</p>", metadata={"content_type": "text/html"},
    )
    with pytest.raises(ValueError, match="approved, reviewed"):
        resolve_approved_html_excerpt(
            source_document_id=document["id"], excerpt="Pending content."
        )


def test_plain_text_or_unknown_content_type_is_not_treated_as_html(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "plain.sqlite"))
    storage.init_db()
    register_source("plain-research", "Plain Research", "manual_import")
    document = ingest_document(
        "plain-research", "Plain", "https://example.org/plain",
        "<p>Not registered as HTML.</p>", metadata={"content_type": "text/plain"},
    )
    review_document(document["id"], "approved", "reviewer-label")
    with pytest.raises(ValueError, match="not registered as text/html"):
        resolve_approved_html_excerpt(
            source_document_id=document["id"], excerpt="Not registered as HTML."
        )


def test_oversized_html_and_excerpt_are_rejected(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="1 MB"):
        extract_html_blocks("x" * 1_000_001)
    document = _approved_html(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="2,000"):
        resolve_approved_html_excerpt(
            source_document_id=document["id"], excerpt="x" * 2_001
        )
