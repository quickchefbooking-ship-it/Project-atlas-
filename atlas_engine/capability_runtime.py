"""Trusted, bounded capability handlers for the Professor execution core.

Only application-owned handlers are installed. Task payloads can select a
registered capability but cannot add handlers, code, credentials or network
access. The first vertical slice is deterministic local arithmetic only.
"""
from __future__ import annotations

import time
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .capability_registry import CapabilityDefinition, CapabilityRegistry
from .executor import safe_execute_local


class CapabilityExecutionError(RuntimeError):
    """A capability failed within its declared execution boundary."""


class CapabilityRuntime:
    def __init__(
        self,
        registry: CapabilityRegistry,
        handlers: Mapping[tuple[str, str], Callable[[dict[str, Any], float], dict[str, Any]]],
    ) -> None:
        if not isinstance(registry, CapabilityRegistry):
            raise TypeError("A trusted CapabilityRegistry is required.")
        copied = dict(handlers)
        if any(registry.get(name, version) is None for name, version in copied):
            raise ValueError("Every handler must have a matching trusted capability definition.")
        self.registry = registry
        self._handlers = MappingProxyType(copied)

    def execute(
        self, capability: str, version: str, payload: dict[str, Any], *,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        definition = self.registry.get(capability, version)
        handler = self._handlers.get((capability, version))
        if definition is None or handler is None:
            raise CapabilityExecutionError("Capability is not installed.")
        definition.validate_input(payload)
        budget = definition.timeout_seconds
        if timeout_seconds is not None:
            if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds < 1:
                raise ValueError("timeout_seconds must be a positive integer.")
            budget = min(budget, timeout_seconds)
        deadline = time.monotonic() + budget
        try:
            result = handler(payload, deadline)
            if time.monotonic() >= deadline:
                raise TimeoutError("Capability execution deadline exceeded.")
            definition.validate_output(result)
            return result
        except Exception as exc:
            raise CapabilityExecutionError("Capability execution failed.") from exc


def _calculate(payload: dict[str, Any], deadline: float) -> dict[str, Any]:
    result = safe_execute_local({
        "description": payload["expression"],
        "_execution_deadline_monotonic": deadline,
    })
    return {"value": result["value"], "kind": "number"}


def build_default_capability_runtime() -> CapabilityRuntime:
    """Build the initial trusted catalogue and its one safe local handler."""
    definition = CapabilityDefinition(
        name="math.calculate",
        version="1.0.0",
        risk_class="local_computation",
        input_schema={
            "type": "object",
            "properties": {
                "expression": {"type": "string", "minLength": 1, "maxLength": 256}
            },
            "required": ["expression"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "value": {"type": "number"},
                "kind": {"type": "string", "const": "number"},
            },
            "required": ["value", "kind"],
            "additionalProperties": False,
        },
        required_scopes=("compute:local",),
        side_effects=False,
        timeout_seconds=10,
        approval_required=False,
    )
    registry = CapabilityRegistry((definition,))
    return CapabilityRuntime(
        registry,
        {definition.identity: _calculate},
    )
