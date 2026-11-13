import pytest

from atlas_engine.capability_registry import CapabilityDefinition, CapabilityRegistry
from atlas_engine.retry_policy import CapabilityRetryContract


def _definition(**overrides):
    values = {
        "name": "research.lookup",
        "version": "1",
        "risk_class": "read_only",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "minLength": 3}},
            "required": ["query"],
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
            "additionalProperties": False,
        },
        "required_scopes": ("public.research.read",),
        "side_effects": False,
        "timeout_seconds": 8,
    }
    values.update(overrides)
    return CapabilityDefinition(**values)


def test_registry_is_application_constructed_and_read_only():
    definition = _definition()
    registry = CapabilityRegistry([definition])
    assert len(registry) == 1
    assert registry.get("research.lookup", "1") is definition
    assert registry.get("research.lookup", "2") is None
    assert registry.list_definitions() == (definition,)
    with pytest.raises(AttributeError):
        registry.register(definition)


def test_registry_rejects_duplicate_name_and_version():
    with pytest.raises(ValueError, match="Duplicate capability"):
        CapabilityRegistry([_definition(), _definition()])


def test_registry_rejects_unvalidated_objects():
    with pytest.raises(ValueError, match="validated capability"):
        CapabilityRegistry([{"name": "task.supplied"}])


def test_schema_metadata_is_deeply_immutable():
    source = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }
    definition = _definition(input_schema=source)
    source["properties"]["query"]["type"] = "integer"
    source["required"].append("admin")
    assert definition.input_schema["properties"]["query"]["type"] == "string"
    assert definition.input_schema["required"] == ("query",)
    with pytest.raises(TypeError):
        definition.input_schema["properties"]["query"]["type"] = "integer"


@pytest.mark.parametrize("risk", ["external_write", "privileged"])
def test_external_and_privileged_capabilities_require_approval(risk):
    with pytest.raises(ValueError, match="require approval"):
        _definition(risk_class=risk, side_effects=True)


def test_read_only_capability_cannot_declare_side_effects():
    with pytest.raises(ValueError, match="read-only"):
        _definition(side_effects=True)


def test_invalid_timeout_and_unknown_risk_are_rejected():
    with pytest.raises(ValueError, match="timeout"):
        _definition(timeout_seconds=31)
    with pytest.raises(ValueError, match="risk class"):
        _definition(risk_class="unrestricted")


def test_required_fields_must_exist_in_schema_properties():
    with pytest.raises(ValueError, match="undeclared property"):
        _definition(input_schema={
            "type": "object", "properties": {}, "required": ["secret"]
        })


def test_remote_schema_references_are_rejected():
    with pytest.raises(ValueError, match="schema references"):
        _definition(input_schema={
            "type": "object", "$ref": "https://example.invalid/schema.json"
        })


def test_retry_opt_in_requires_proven_contract_and_scoped_idempotency_key():
    contract = CapabilityRetryContract(
        capability_name="research.lookup",
        version="1",
        idempotent=True,
        side_effects_declared=True,
        duplicate_suppression_verified=True,
        verification_evidence="tests/test_capability_registry.py::test_provider_deduplicates",
        retryable_error_codes=frozenset({"temporary_unavailable"}),
    )
    with pytest.raises(ValueError, match="idempotency-key scope"):
        _definition(retry_contract=contract)
    enabled = _definition(
        retry_contract=contract,
        idempotency_key_scope="tenant+capability+request",
    )
    assert enabled.retry_contract is contract


def test_unsafe_retry_contract_is_rejected():
    contract = CapabilityRetryContract(
        capability_name="research.lookup",
        version="1",
        idempotent=True,
        side_effects_declared=True,
        duplicate_suppression_verified=False,
        verification_evidence="unverified",
        retryable_error_codes=frozenset({"temporary_unavailable"}),
    )
    with pytest.raises(ValueError, match="duplicate suppression"):
        _definition(
            retry_contract=contract,
            idempotency_key_scope="tenant+request",
        )


def test_nested_remote_schema_references_and_non_finite_numbers_are_rejected():
    with pytest.raises(ValueError, match="schema references"):
        _definition(input_schema={
            "type": "object",
            "properties": {
                "nested": {"type": "object", "properties": {
                    "value": {"$ref": "https://example.invalid/schema.json"}
                }}
            },
        })
    with pytest.raises(ValueError, match="JSON-compatible"):
        _definition(input_schema={
            "type": "object",
            "properties": {"limit": {"type": "number", "default": float("inf")}},
        })


def test_retry_contract_must_match_registered_capability_identity():
    contract = CapabilityRetryContract(
        capability_name="another.capability",
        version="1",
        idempotent=True,
        side_effects_declared=True,
        duplicate_suppression_verified=True,
        verification_evidence="tests/test_capability_registry.py::test_provider_deduplicates",
        retryable_error_codes=frozenset({"temporary_unavailable"}),
    )
    with pytest.raises(ValueError, match="identity must match"):
        _definition(
            retry_contract=contract,
            idempotency_key_scope="tenant+request",
        )


def test_input_and_output_are_validated_against_declared_schemas():
    definition = _definition()
    definition.validate_input({"query": "atlas"})
    definition.validate_output({"title": "Atlas research"})
    with pytest.raises(ValueError, match="input failed schema validation"):
        definition.validate_input({"query": "x"})
    with pytest.raises(ValueError, match="output failed schema validation"):
        definition.validate_output({"title": 42})


def test_unknown_properties_are_rejected():
    definition = _definition()
    with pytest.raises(ValueError, match="input failed schema validation"):
        definition.validate_input({"query": "atlas", "admin": True})


@pytest.mark.parametrize("payload", [
    ["not", "an", "object"],
    {"query": float("nan")},
    {"query": object()},
])
def test_non_object_and_non_json_payloads_are_rejected(payload):
    with pytest.raises(ValueError):
        _definition().validate_input(payload)


def test_payload_size_is_bounded():
    definition = _definition()
    with pytest.raises(ValueError, match="64-KiB limit"):
        definition.validate_input({"query": "x" * (64 * 1024)})


def test_invalid_json_schema_is_rejected_at_definition_time():
    with pytest.raises(ValueError, match="valid Draft 2020-12 schema"):
        _definition(input_schema={
            "type": "object",
            "properties": {"query": {"type": "not-a-json-schema-type"}},
        })


def test_schema_validation_error_does_not_echo_untrusted_value():
    definition = _definition()
    secret = "do-not-echo-this-secret"
    with pytest.raises(ValueError) as captured:
        definition.validate_input({"query": secret})
    assert secret not in str(captured.value)
