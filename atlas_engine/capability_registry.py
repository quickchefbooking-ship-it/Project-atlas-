"""Application-owned, immutable capability catalogue for AtlasOnePro.

This is a metadata registry only: it does not execute capabilities, load plugins,
accept task-supplied registrations, or grant credentials. Definitions must be
constructed by trusted application code at startup.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, Mapping

from .retry_policy import CapabilityRetryContract


_ALLOWED_RISK_CLASSES = frozenset({
    "read_only",
    "local_write",
    "external_write",
    "privileged",
})
_EXTERNAL_RISKS = frozenset({"external_write", "privileged"})


def _freeze(value: Any) -> Any:
    """Recursively copy schema metadata into immutable containers."""
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError("Capability schemas may contain only JSON-compatible values.")


def _validate_schema_shape(schema: Mapping[str, Any], field: str) -> None:
    if not isinstance(schema, Mapping):
        raise ValueError(f"{field} must be a JSON Schema object.")
    if schema.get("type") != "object":
        raise ValueError(f"{field} must describe an object.")
    if not isinstance(schema.get("properties", {}), Mapping):
        raise ValueError(f"{field}.properties must be an object.")
    required = schema.get("required", ())
    if not isinstance(required, (list, tuple)) or any(
        not isinstance(item, str) for item in required
    ):
        raise ValueError(f"{field}.required must be a list of strings.")
    properties = schema.get("properties", {})
    if any(item not in properties for item in required):
        raise ValueError(f"{field}.required contains an undeclared property.")
    def reject_references(value: Any) -> None:
        if isinstance(value, Mapping):
            if "$ref" in value or "$dynamicRef" in value:
                raise ValueError(
                    f"{field} cannot use external or recursive schema references."
                )
            for nested in value.values():
                reject_references(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                reject_references(nested)

    reject_references(schema)


@dataclass(frozen=True)
class CapabilityDefinition:
    """One versioned capability declaration supplied by application code."""

    name: str
    version: str
    risk_class: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    required_scopes: tuple[str, ...] = ()
    side_effects: bool = False
    timeout_seconds: int = 10
    approval_required: bool = False
    idempotency_key_scope: str | None = None
    retry_contract: CapabilityRetryContract | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Capability name is required.")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("Capability version is required.")
        if self.risk_class not in _ALLOWED_RISK_CLASSES:
            raise ValueError("Unsupported capability risk class.")
        if type(self.side_effects) is not bool or type(self.approval_required) is not bool:
            raise ValueError("Capability side-effect and approval flags must be booleans.")
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, int) or not 1 <= self.timeout_seconds <= 30:
            raise ValueError("Capability timeout must be between 1 and 30 seconds.")
        if not isinstance(self.required_scopes, (list, tuple)) or any(
            not isinstance(scope, str) or not scope.strip() for scope in self.required_scopes
        ):
            raise ValueError("Capability scopes must be non-empty strings.")
        if len(set(self.required_scopes)) != len(self.required_scopes):
            raise ValueError("Capability scopes must be unique.")
        if self.risk_class == "read_only" and self.side_effects:
            raise ValueError("A read-only capability cannot declare side effects.")
        if self.risk_class in _EXTERNAL_RISKS and not self.approval_required:
            raise ValueError("External and privileged capabilities require approval.")
        if self.side_effects and self.risk_class == "read_only":
            raise ValueError("Side effects cannot be attached to read-only capabilities.")
        if self.idempotency_key_scope is not None and (
            not isinstance(self.idempotency_key_scope, str)
            or not self.idempotency_key_scope.strip()
            or len(self.idempotency_key_scope) > 128
        ):
            raise ValueError("Idempotency key scope must contain 1 to 128 characters.")
        _validate_schema_shape(self.input_schema, "input_schema")
        _validate_schema_shape(self.output_schema, "output_schema")
        if self.retry_contract is not None:
            if not isinstance(self.retry_contract, CapabilityRetryContract):
                raise ValueError("retry_contract must be a validated retry contract.")
            if (
                self.retry_contract.capability_name != self.name.strip()
                or self.retry_contract.version != self.version.strip()
            ):
                raise ValueError("Retry contract identity must match the capability.")
            if not self.retry_contract.retry_is_safe:
                raise ValueError("Retry contract does not prove safe duplicate suppression.")
            if self.idempotency_key_scope is None:
                raise ValueError("Retryable capabilities require an idempotency-key scope.")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "version", self.version.strip())
        object.__setattr__(self, "required_scopes", tuple(sorted(self.required_scopes)))
        object.__setattr__(self, "input_schema", _freeze(self.input_schema))
        object.__setattr__(self, "output_schema", _freeze(self.output_schema))

    def validate_input(self, value: Any) -> None:
        """Reject malformed inputs before a registered handler is invoked."""
        from .capability_schema import validate_json_value
        validate_json_value(value, self.input_schema, path=f"{self.name}.input")

    def validate_output(self, value: Any) -> None:
        """Reject malformed handler outputs before they are returned to a caller."""
        from .capability_schema import validate_json_value
        validate_json_value(value, self.output_schema, path=f"{self.name}.output")

    @property
    def identity(self) -> tuple[str, str]:
        return self.name, self.version


class CapabilityRegistry:
    """Read-only registry created from trusted application-owned definitions.

    There is deliberately no runtime register/update method and no API for
    task payloads to add capabilities.
    """

    def __init__(self, definitions: tuple[CapabilityDefinition, ...] | list[CapabilityDefinition] = ()):
        if not isinstance(definitions, (tuple, list)):
            raise ValueError("Registry definitions must be a list or tuple.")
        indexed: dict[tuple[str, str], CapabilityDefinition] = {}
        for definition in definitions:
            if not isinstance(definition, CapabilityDefinition):
                raise ValueError("Registry accepts only validated capability definitions.")
            if definition.identity in indexed:
                raise ValueError("Duplicate capability name and version.")
            indexed[definition.identity] = definition
        self._definitions = MappingProxyType(indexed)

    def get(self, name: str, version: str) -> CapabilityDefinition | None:
        return self._definitions.get((name, version))

    def list_definitions(self) -> tuple[CapabilityDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))

    def __len__(self) -> int:
        return len(self._definitions)
