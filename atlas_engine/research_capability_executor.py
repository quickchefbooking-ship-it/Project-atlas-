"""Read-only executor for Professor's registered research capabilities.

This is an internal application service, not an HTTP endpoint. It requires scopes
supplied by a trusted caller, validates every proposed call, and never executes
model-generated code or arbitrary URLs.
"""
from __future__ import annotations

from typing import Any, Callable

from .capability_registry import CapabilityRegistry
from .model_provider import ProposedCapabilityCall
from .public_research_adapters import (
    fetch_github_repository,
    fetch_huggingface_resource,
    search_crossref_works,
    search_uk_legislation,
)
from .research_capabilities import build_research_registry, validate_research_capability_call
from .source_adapters import stage_adapter_results
from .source_division import retrieve


class _StaticResultsAdapter:
    def __init__(self, source_id: str, documents: list[Any]):
        self.source_id = source_id
        self._documents = documents

    def search(self, _query: str, limit: int = 10):
        return self._documents[:limit]


class ResearchCapabilityExecutor:
    """Execute only the fixed read-only source adapters declared in the registry."""

    REQUIRED_SOURCE_IDS = {
        "crossref.search": "crossref-public",
        "github.repository_metadata": "github-public",
        "huggingface.resource_metadata": "huggingface-public",
        "legislation.search": "uk-legislation",
    }

    def __init__(
        self,
        registry: CapabilityRegistry | None = None,
        *,
        source_retriever: Callable[..., list[dict[str, Any]]] | None = None,
        adapter_functions: dict[str, Callable[..., Any]] | None = None,
    ):
        self.registry = registry or build_research_registry()
        self._source_retriever = source_retriever or retrieve
        self._adapter_functions = adapter_functions or {
            "crossref.search": search_crossref_works,
            "github.repository_metadata": fetch_github_repository,
            "huggingface.resource_metadata": fetch_huggingface_resource,
            "legislation.search": search_uk_legislation,
        }

    def execute(
        self,
        proposed: ProposedCapabilityCall,
        *,
        granted_scopes: frozenset[str],
    ) -> dict[str, Any]:
        if not isinstance(granted_scopes, frozenset) or any(
            not isinstance(scope, str) for scope in granted_scopes
        ):
            raise TypeError("Trusted immutable capability scopes are required.")

        definition, arguments = validate_research_capability_call(self.registry, proposed)
        missing_scopes = set(definition.required_scopes) - set(granted_scopes)
        if missing_scopes:
            raise PermissionError("The caller does not hold the required research capability scope.")
        if definition.risk_class != "read_only" or definition.side_effects:
            raise PermissionError("Research executor accepts read-only capabilities only.")

        capability_id = definition.name
        if capability_id == "source.approved_retrieval":
            records = self._source_retriever(arguments.query, limit=arguments.limit)
            return {
                "capability_id": capability_id,
                "capability_version": definition.version,
                "evidence": records,
                "evidence_state": "approved_existing_knowledge",
            }

        source_id = self.REQUIRED_SOURCE_IDS[capability_id]
        if capability_id == "crossref.search":
            documents = self._adapter_functions[capability_id](arguments.query, limit=arguments.limit)
        elif capability_id == "legislation.search":
            documents = self._adapter_functions[capability_id](arguments.query, limit=arguments.limit)
        elif capability_id == "github.repository_metadata":
            documents = [self._adapter_functions[capability_id](arguments.identifier)]
        elif capability_id == "huggingface.resource_metadata":
            documents = [self._adapter_functions[capability_id](
                arguments.identifier, resource_type=arguments.resource_type
            )]
        else:
            raise ValueError("Research capability is not implemented.")

        staged = stage_adapter_results(
            _StaticResultsAdapter(source_id, documents),
            getattr(arguments, "query", getattr(arguments, "identifier", "")),
            limit=definition.max_results,
        )
        evidence = [
            {
                "document_id": item["id"],
                "source_id": item["source_id"],
                "title": item["title"],
                "uri": item["uri"],
                "content": item["content"],
                "content_sha256": item["content_sha256"],
                "trust_level": item["trust_level"],
                "review_state": item["state"],
                "metadata_json": item["metadata_json"],
            }
            for item in staged
        ]
        return {
            "capability_id": capability_id,
            "capability_version": definition.version,
            "evidence": evidence,
            "evidence_state": "pending_unverified_external_source",
        }
