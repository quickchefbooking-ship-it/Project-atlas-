import hashlib
import json

import pytest
from pydantic import ValidationError

from atlas_engine.model_provider import (
    DeterministicMockProvider,
    ProposedCapabilityCall,
    ProviderError,
    ProviderRequest,
)


def _request(**overrides):
    values = {
        "system_instruction": "Return a structured research plan.",
        "task_input": "Compare two public research sources.",
        "output_format": "json",
        "correlation_id": "test-run-001",
    }
    values.update(overrides)
    return ProviderRequest(**values)


def test_mock_provider_is_explicitly_non_ai_and_has_no_external_side_effects():
    provider = DeterministicMockProvider()
    descriptor = provider.describe()

    assert descriptor.provider_id == "deterministic_mock"
    assert descriptor.external_network is False
    assert descriptor.paid_service is False

    response = provider.generate(_request(), timeout_seconds=2)

    assert response.provider_id == "deterministic_mock"
    assert response.model_id == "fixture-v1"
    assert response.proposed_capability_calls == []
    assert response.output_sha256 == hashlib.sha256(response.output_text.encode()).hexdigest()
    assert json.loads(response.output_text)["status"] == "mock"


def test_provider_request_rejects_unknown_fields_and_invalid_budgets():
    with pytest.raises(ValidationError):
        _request(unrestricted_tools=True)
    with pytest.raises(ValidationError):
        _request(temperature=2)
    with pytest.raises(ValidationError):
        _request(max_output_tokens=100_000)
    with pytest.raises(ValidationError):
        _request(task_input=" ")


def test_mock_provider_rejects_invalid_json_fixture_without_leaking_fixture():
    provider = DeterministicMockProvider("not-json")
    with pytest.raises(ProviderError, match="not valid JSON"):
        provider.generate(_request(), timeout_seconds=2)


def test_mock_provider_enforces_timeout_argument_bounds():
    provider = DeterministicMockProvider()
    with pytest.raises(ValueError):
        provider.generate(_request(), timeout_seconds=0)
    with pytest.raises(ValueError):
        provider.generate(_request(), timeout_seconds=31)
    with pytest.raises(ValueError):
        provider.generate(_request(), timeout_seconds=True)


def test_capability_call_is_only_a_validated_proposal():
    proposal = ProposedCapabilityCall(
        capability_id="crossref.search",
        capability_version="1.0",
        arguments={"query": "agent evaluation"},
    )
    assert proposal.capability_id == "crossref.search"
    assert proposal.arguments["query"] == "agent evaluation"

    with pytest.raises(ValidationError):
        ProposedCapabilityCall(
            capability_id="../../shell",
            capability_version="1.0",
        )
    with pytest.raises(ValidationError):
        ProposedCapabilityCall(
            capability_id="crossref.search",
            capability_version="1.0",
            command="curl https://example.org",
        )


def test_provider_output_is_bounded():
    with pytest.raises(ValueError):
        DeterministicMockProvider("x" * 24_001)
