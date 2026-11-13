"""Trusted research capability definitions for Professor.

The registry contains only bounded, read-only source operations already present in
the codebase. This module validates proposed calls; it does not execute them.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .capability_registry import CapabilityDefinition, CapabilityRegistry
from .model_provider import ProposedCapabilityCall


class ResearchQueryArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=3, max_length=120)
    limit: int = Field(default=5, ge=1, le=5)


class GitHubRepositoryArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    identifier: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")


class HuggingFaceResourceArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    identifier: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,100}(?:/[A-Za-z0-9_.-]{1,100})?$")
    resource_type: str = Field(default="model", pattern=r"^(model|dataset)$")


class ApprovedSourceSearchArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=2, max_length=300)
    limit: int = Field(default=5, ge=1, le=10)


def _object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def build_research_registry() -> CapabilityRegistry:
    """Create the closed, application-owned research capability catalogue."""
    query_schema = _object_schema(
        {
            "query": {"type": "string", "minLength": 3, "maxLength": 120},
            "limit": {"type": "integer", "minimum": 1, "maximum": 5, "default": 5},
        },
        ["query"],
    )
    identifier_schema = _object_schema(
        {"identifier": {"type": "string", "minLength": 3, "maxLength": 201}},
        ["identifier"],
    )
    hf_schema = _object_schema(
        {
            "identifier": {"type": "string", "minLength": 1, "maxLength": 201},
            "resource_type": {"type": "string", "enum": ["model", "dataset"], "default": "model"},
        },
        ["identifier"],
    )
    approved_schema = _object_schema(
        {
            "query": {"type": "string", "minLength": 2, "maxLength": 300},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
        },
        ["query"],
    )
    output_schema = _object_schema(
        {
            "title": {"type": "string"},
            "uri": {"type": "string", "format": "uri"},
            "content_sha256": {"type": "string"},
            "state": {"type": "string", "enum": ["pending", "approved"]},
        },
        ["title", "uri", "content_sha256", "state"],
    )
    definitions = [
        CapabilityDefinition(
            name="crossref.search", version="1", risk_class="read_only",
            input_schema=query_schema, output_schema=output_schema,
            required_scopes=("public.research.read",), timeout_seconds=10,
        ),
        CapabilityDefinition(
            name="github.repository_metadata", version="1", risk_class="read_only",
            input_schema=identifier_schema, output_schema=output_schema,
            required_scopes=("public.research.read",), timeout_seconds=10,
        ),
        CapabilityDefinition(
            name="huggingface.resource_metadata", version="1", risk_class="read_only",
            input_schema=hf_schema, output_schema=output_schema,
            required_scopes=("public.research.read",), timeout_seconds=10,
        ),
        CapabilityDefinition(
            name="legislation.search", version="1", risk_class="read_only",
            input_schema=query_schema, output_schema=output_schema,
            required_scopes=("public.research.read",), timeout_seconds=10,
        ),
        CapabilityDefinition(
            name="source.approved_retrieval", version="1", risk_class="read_only",
            input_schema=approved_schema, output_schema=output_schema,
            required_scopes=("knowledge.approved.read",), timeout_seconds=2,
        ),
    ]
    return CapabilityRegistry(definitions)


_ARGUMENT_MODELS: dict[str, type[BaseModel]] = {
    "crossref.search": ResearchQueryArguments,
    "legislation.search": ResearchQueryArguments,
    "github.repository_metadata": GitHubRepositoryArguments,
    "huggingface.resource_metadata": HuggingFaceResourceArguments,
    "source.approved_retrieval": ApprovedSourceSearchArguments,
}


def validate_research_capability_call(
    registry: CapabilityRegistry,
    proposed: ProposedCapabilityCall,
) -> tuple[CapabilityDefinition, BaseModel]:
    """Validate identity and arguments against trusted code-owned definitions."""
    if not isinstance(registry, CapabilityRegistry):
        raise TypeError("A trusted application capability registry is required.")
    if not isinstance(proposed, ProposedCapabilityCall):
        raise TypeError("A validated capability proposal is required.")
    definition = registry.get(proposed.capability_id, proposed.capability_version)
    if definition is None or proposed.capability_id not in _ARGUMENT_MODELS:
        raise ValueError("Capability is not registered for Professor research.")
    try:
        arguments = _ARGUMENT_MODELS[proposed.capability_id].model_validate(proposed.arguments)
    except ValidationError as exc:
        raise ValueError("Capability arguments do not match the registered input contract.") from exc
    return definition, arguments
