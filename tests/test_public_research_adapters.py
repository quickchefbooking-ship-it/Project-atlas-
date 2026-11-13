from fastapi.testclient import TestClient
import pytest

import app as app_module
from atlas_engine import storage
from atlas_engine.public_research_adapters import (
    PublicSourceError,
    fetch_github_repository,
    fetch_huggingface_resource,
)
from atlas_engine.source_adapters import SourceDocument


def _client(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "public-sources.db"))
    storage.init_db()
    monkeypatch.setattr(app_module, "API_REQUIRE_AUTH", True)
    monkeypatch.setattr(app_module, "API_KEY", "public-source-test-key")
    monkeypatch.delenv("ATLAS_API_KEY", raising=False)
    return TestClient(app_module.app)


def _headers():
    return {"X-API-Key": "public-source-test-key"}


def test_github_adapter_normalizes_public_repository_metadata(monkeypatch):
    monkeypatch.setattr(
        "atlas_engine.public_research_adapters._get_json",
        lambda url: {
            "full_name": "octocat/Hello-World",
            "html_url": "https://github.com/octocat/Hello-World",
            "description": "A public example repository",
            "language": "Python",
            "topics": ["example"],
            "license": {"spdx_id": "MIT"},
            "stargazers_count": 10,
            "updated_at": "2026-11-01T00:00:00Z",
        },
    )
    document = fetch_github_repository("octocat/Hello-World")
    assert document.uri == "https://github.com/octocat/Hello-World"
    assert "A public example repository" in document.content
    assert document.metadata["provider"] == "github"
    assert document.metadata["retrieved_at"]


def test_huggingface_adapter_supports_public_models_and_datasets(monkeypatch):
    seen = []
    def fake_get_json(url):
        seen.append(url)
        return {"id": "open-model/demo", "author": "open-model", "tags": ["text-generation"], "private": False}
    monkeypatch.setattr("atlas_engine.public_research_adapters._get_json", fake_get_json)
    model = fetch_huggingface_resource("open-model/demo", "model")
    dataset = fetch_huggingface_resource("open-model/demo", "dataset")
    assert seen == [
        "https://huggingface.co/api/models/open-model/demo",
        "https://huggingface.co/api/datasets/open-model/demo",
    ]
    assert model.uri == "https://huggingface.co/open-model/demo"
    assert dataset.uri == "https://huggingface.co/datasets/open-model/demo"


@pytest.mark.parametrize("identifier", ["../secret", "https://evil.example/x", "owner/repo?x=1", "owner"])
def test_github_adapter_rejects_malformed_identifiers(identifier):
    with pytest.raises(PublicSourceError):
        fetch_github_repository(identifier)


def test_provider_response_limit_is_enforced(monkeypatch):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, limit):
            return b"x" * limit
    monkeypatch.setattr("atlas_engine.public_research_adapters.urlopen", lambda *args, **kwargs: Response())
    with pytest.raises(PublicSourceError, match="1 MB"):
        from atlas_engine.public_research_adapters import _get_json
        _get_json("https://api.github.com/repos/octocat/Hello-World")


def test_authenticated_fetch_stages_github_metadata_pending(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    with client:
        pass
    document = SourceDocument(
        title="GitHub repository: octocat/Hello-World",
        uri="https://github.com/octocat/Hello-World",
        content="Public GitHub repository metadata: Python project.",
        metadata={"provider": "github", "retrieved_at": "2026-11-13T00:00:00+00:00"},
    )
    monkeypatch.setattr(app_module, "fetch_github_repository", lambda identifier: document)
    assert client.post("/sources/fetch", json={"provider": "github", "identifier": "octocat/Hello-World"}).status_code == 401
    response = client.post(
        "/sources/fetch",
        headers=_headers(),
        json={"provider": "github", "identifier": "octocat/Hello-World", "resource_type": "repository"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "staged_for_review"
    assert response.json()["documents"][0]["state"] == "pending"
    assert response.json()["documents"][0]["trust_level"] == "unverified"
    assert storage.get_source("github-public") is not None


def test_huggingface_fetch_stages_dataset_metadata(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    with client:
        pass
    document = SourceDocument(
        title="Hugging Face dataset: demo/data",
        uri="https://huggingface.co/datasets/demo/data",
        content="Public dataset metadata.",
        metadata={"provider": "huggingface", "resource_type": "dataset"},
    )
    monkeypatch.setattr(app_module, "fetch_huggingface_resource", lambda identifier, resource_type: document)
    response = client.post(
        "/sources/fetch",
        headers=_headers(),
        json={"provider": "huggingface", "identifier": "demo/data", "resource_type": "dataset"},
    )
    assert response.status_code == 200
    assert response.json()["documents"][0]["source_id"] == "huggingface-public"
    assert response.json()["documents"][0]["state"] == "pending"


def test_fetch_rejects_provider_resource_mismatch(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    with client:
        pass
    response = client.post(
        "/sources/fetch",
        headers=_headers(),
        json={"provider": "github", "identifier": "octocat/Hello-World", "resource_type": "dataset"},
    )
    assert response.status_code == 422



def test_uk_legislation_adapter_searches_official_feed_and_extracts_text(monkeypatch):
    feed = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Equality Act 2010</title>
        <link rel="alternate" href="https://www.legislation.gov.uk/ukpga/2010/15"/>
      </entry>
    </feed>"""
    law = """<?xml version="1.0"?>
    <Legislation xmlns="http://www.legislation.gov.uk/namespaces/legislation">
      <Title>Equality Act 2010</Title><Body><P1>Discrimination must not occur.</P1></Body>
    </Legislation>"""
    requested = []
    def fake_get_xml(url):
        requested.append(url)
        return feed if "data.feed" in url else law
    monkeypatch.setattr("atlas_engine.public_research_adapters._get_xml_text", fake_get_xml)
    from atlas_engine.public_research_adapters import search_uk_legislation
    documents = search_uk_legislation("Equality Act", "ukpga", limit=2)
    assert len(documents) == 1
    assert documents[0].title == "Equality Act 2010"
    assert documents[0].uri == "https://www.legislation.gov.uk/ukpga/2010/15"
    assert "Discrimination must not occur." in documents[0].content
    assert documents[0].metadata["publisher"] == "The National Archives"
    assert "results-count=2" in requested[0]
    assert requested[1].endswith("/data.xml")


@pytest.mark.parametrize("query,kind", [("x", "ukpga"), ("Equality Act", "madeup")])
def test_uk_legislation_adapter_rejects_invalid_query_or_type(query, kind):
    from atlas_engine.public_research_adapters import search_uk_legislation
    with pytest.raises(PublicSourceError):
        search_uk_legislation(query, kind)


def test_authenticated_legislation_fetch_stages_multiple_documents(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    with client:
        pass
    docs = [
        SourceDocument(
            title="Equality Act 2010",
            uri="https://www.legislation.gov.uk/ukpga/2010/15",
            content="Official text of the Equality Act 2010.",
            metadata={"provider": "legislation.gov.uk", "retrieved_at": "2026-11-13T00:00:00+00:00"},
        ),
        SourceDocument(
            title="Equality Act 2010 (Commencement No. 1) Order",
            uri="https://www.legislation.gov.uk/uksi/2010/2317",
            content="Official commencement order text.",
            metadata={"provider": "legislation.gov.uk", "retrieved_at": "2026-11-13T00:00:00+00:00"},
        ),
    ]
    monkeypatch.setattr(app_module, "search_uk_legislation", lambda query, kind, limit=5: docs)
    response = client.post(
        "/sources/fetch",
        headers=_headers(),
        json={"provider": "legislation", "identifier": "Equality Act", "resource_type": "ukpga"},
    )
    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert all(item["state"] == "pending" for item in response.json()["documents"])
    assert storage.get_source("uk-legislation") is not None


def test_legislation_fetch_returns_not_found_for_empty_results(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    with client:
        pass
    monkeypatch.setattr(app_module, "search_uk_legislation", lambda query, kind, limit=5: [])
    response = client.post(
        "/sources/fetch",
        headers=_headers(),
        json={"provider": "legislation", "identifier": "No such Act", "resource_type": "ukpga"},
    )
    assert response.status_code == 404



def test_crossref_adapter_normalizes_bibliographic_metadata(monkeypatch):
    seen = []
    def fake_get_json(url):
        seen.append(url)
        return {
            "message": {
                "items": [{
                    "DOI": "10.1234/example.2026",
                    "title": ["A study of safe AI systems"],
                    "author": [{"given": "Ada", "family": "Lovelace"}],
                    "publisher": "Example Academic Press",
                    "type": "journal-article",
                    "is-referenced-by-count": 12,
                    "abstract": "<jats:p>Abstract text supplied by the publisher.</jats:p>",
                    "URL": "https://publisher.example/article",
                }]
            }
        }
    monkeypatch.setattr("atlas_engine.public_research_adapters._get_json", fake_get_json)
    from atlas_engine.public_research_adapters import search_crossref_works
    documents = search_crossref_works("safe AI systems", limit=3)
    assert len(documents) == 1
    assert documents[0].title == "A study of safe AI systems"
    assert documents[0].uri == "https://doi.org/10.1234/example.2026"
    assert "Ada Lovelace" in documents[0].content
    assert documents[0].metadata["provider"] == "crossref"
    assert documents[0].metadata["full_text_not_fetched"] is True
    assert "rows=3" in seen[0]


@pytest.mark.parametrize("query", ["AI", "x" * 161])
def test_crossref_rejects_invalid_search_query(query):
    from atlas_engine.public_research_adapters import search_crossref_works
    with pytest.raises(PublicSourceError):
        search_crossref_works(query)


def test_authenticated_crossref_search_stages_pending_records(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    with client:
        pass
    docs = [
        SourceDocument(
            title="A study of safe AI systems",
            uri="https://doi.org/10.1234/example.2026",
            content="Crossref metadata for a scholarly work.",
            metadata={"provider": "crossref", "resource_type": "scholarly_work"},
        )
    ]
    monkeypatch.setattr(app_module, "search_crossref_works", lambda query, limit=5: docs)
    response = client.post(
        "/sources/fetch",
        headers=_headers(),
        json={"provider": "crossref", "identifier": "safe AI systems", "resource_type": "scholarly_work"},
    )
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["documents"][0]["state"] == "pending"
    assert response.json()["documents"][0]["source_id"] == "crossref-public"
    assert storage.get_source("crossref-public") is not None
