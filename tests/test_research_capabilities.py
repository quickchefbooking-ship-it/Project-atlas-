import pytest
from pydantic import ValidationError

from atlas_engine.model_provider import ProposedCapabilityCall
from atlas_engine.research_capabilities import (
    build_research_registry,
    validate_research_capability_call,
)


def test_research_registry_contains_only_expected_read_only_capabilities():
    registry = build_research_registry()
    definitions = registry.list_definitions()

    assert {item.name for item in definitions} == {
        "crossref.search",
        "github.repository_metadata",
        "huggingface.resource_metadata",
        "legislation.search",
        "source.approved_retrieval",
    }
    assert all(item.risk_class == "read_only" for item in definitions)
    assert all(not item.side_effects for item in definitions)


def test_registered_capability_arguments_are_validated():
    registry = build_research_registry()
    definition, arguments = validate_research_capability_call(
        registry,
        ProposedCapabilityCall(
            capability_id="crossref.search",
            capability_version="1",
            arguments={"query": "AI research agents", "limit": 3},
        ),
    )

    assert definition.name == "crossref.search"
    assert arguments.query == "AI research agents"
    assert arguments.limit == 3


def test_registry_rejects_unknown_capabilities_and_versions():
    registry = build_research_registry()
    with pytest.raises(ValueError, match="not registered"):
        validate_research_capability_call(
            registry,
            ProposedCapabilityCall(
                capability_id="shell.exec",
                capability_version="1",
                arguments={},
            ),
        )
    with pytest.raises(ValueError, match="not registered"):
        validate_research_capability_call(
            registry,
            ProposedCapabilityCall(
                capability_id="crossref.search",
                capability_version="999",
                arguments={"query": "AI research agents"},
            ),
        )


def test_registry_rejects_extra_or_invalid_arguments_without_echoing_values():
    registry = build_research_registry()
    with pytest.raises(ValueError, match="input contract"):
        validate_research_capability_call(
            registry,
            ProposedCapabilityCall(
                capability_id="crossref.search",
                capability_version="1",
                arguments={"query": "AI research agents", "admin": "secret"},
            ),
        )
    with pytest.raises(ValueError, match="input contract"):
        validate_research_capability_call(
            registry,
            ProposedCapabilityCall(
                capability_id="github.repository_metadata",
                capability_version="1",
                arguments={"identifier": "../../etc/passwd"},
            ),
        )


def test_registry_rejects_non_registered_capability_call_object():
    registry = build_research_registry()
    with pytest.raises(TypeError):
        validate_research_capability_call(registry, {"capability_id": "crossref.search"})
