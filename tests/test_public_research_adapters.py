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
    assert response.json()["document"]["state"] == "pending"
    assert response.json()["document"]["trust_level"] == "unverified"
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
    assert response.json()["document"]["source_id"] == "huggingface-public"
    assert response.json()["document"]["state"] == "pending"


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
