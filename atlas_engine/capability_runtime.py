"""Trusted, bounded capability handlers for the Professor execution core.

Only application-owned handlers are installed. Task payloads can select a
registered capability but cannot add handlers, code, credentials or network
access. The initial vertical slice combines deterministic local arithmetic
with read-only scholarly metadata retrieval.
"""
from __future__ import annotations

import json
import time
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .capability_registry import CapabilityDefinition, CapabilityRegistry
from .executor import safe_execute_local
from .evidence_engine import build_evidence_bundle
from .evidence_evaluation import evaluate_evidence_bundle
from .public_research_adapters import PublicSourceError, search_crossref_works


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

    def input_for_objective(self, capability: str, version: str, objective: str, *, dependency_outputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Map trusted plan text or completed dependency outputs to a registered input."""
        definition = self.registry.get(capability, version)
        if definition is None:
            raise CapabilityExecutionError("Capability is not installed.")
        properties = definition.input_schema.get("properties", {})
        required = definition.input_schema.get("required", ())
        if capability == "research.evidence.bundle":
            if "sources" not in required or not isinstance(dependency_outputs, Mapping):
                raise CapabilityExecutionError("Evidence bundling requires completed dependency outputs.")
            sources = []
            for output in dependency_outputs.values():
                if not isinstance(output, Mapping) or not isinstance(output.get("sources"), list):
                    continue
                for source in output["sources"]:
                    if not isinstance(source, Mapping):
                        raise CapabilityExecutionError("A dependency returned an invalid source record.")
                    sources.append({
                        "title": source.get("title"),
                        "uri": source.get("uri"),
                        "doi": source.get("doi") or None,
                        "publisher": source.get("publisher", ""),
                        "retrieved_at": source.get("retrieved_at", ""),
                        "claims": [],
                    })
            if not sources:
                raise CapabilityExecutionError("No source records were available from completed dependencies.")
            return {"sources": sources[:20]}
        if capability == "research.evidence.evaluate":
            if "bundle" not in required or not isinstance(dependency_outputs, Mapping):
                raise CapabilityExecutionError("Evidence evaluation requires a completed evidence-bundle dependency.")
            for output in dependency_outputs.values():
                if isinstance(output, Mapping) and output.get("schema_version") == 1 and isinstance(output.get("claims"), list) and isinstance(output.get("sources"), list):
                    return {"bundle": dict(output)}
            raise CapabilityExecutionError("No completed evidence bundle was available from direct dependencies.")
        string_fields = [
            field for field in required
            if field in properties and properties[field].get("type") == "string"
        ]
        if len(string_fields) != 1:
            raise CapabilityExecutionError("Capability requires an unsupported input mapping.")
        payload: dict[str, Any] = {string_fields[0]: objective}
        # The only supported non-text required input is a bounded result limit.
        # It is selected by application policy, never by untrusted plan text.
        for field in required:
            if field == string_fields[0]:
                continue
            field_schema = properties[field]
            if field != "limit" or field_schema.get("type") != "integer":
                raise CapabilityExecutionError("Capability requires an unsupported input mapping.")
            payload[field] = min(3, field_schema.get("maximum", 3))
        return payload

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


def _evidence_bundle(payload: dict[str, Any], deadline: float) -> dict[str, Any]:
    if time.monotonic() >= deadline:
        raise TimeoutError("Evidence bundling deadline exceeded.")
    result = build_evidence_bundle(payload["sources"])
    if time.monotonic() >= deadline:
        raise TimeoutError("Evidence bundling deadline exceeded.")
    return result


def _evidence_evaluate(payload: dict[str, Any], deadline: float) -> dict[str, Any]:
    if time.monotonic() >= deadline:
        raise TimeoutError("Evidence evaluation deadline exceeded.")
    result = evaluate_evidence_bundle(payload["bundle"])
    if time.monotonic() >= deadline:
        raise TimeoutError("Evidence evaluation deadline exceeded.")
    return result


def _crossref_search(payload: dict[str, Any], deadline: float) -> dict[str, Any]:
    # The adapter has an eight-second transport ceiling. Refuse to start a
    # request when the plan budget cannot contain that bounded call.
    if deadline - time.monotonic() < 8.5:
        raise TimeoutError("Research step budget is shorter than the bounded provider request.")
    documents = search_crossref_works(payload["query"], limit=payload["limit"])
    if time.monotonic() >= deadline:
        raise TimeoutError("Research deadline exceeded.")
    sources = []
    for document in documents[:payload["limit"]]:
        # Crossref abstracts may contain publisher markup. Treat all returned
        # text as untrusted source material, never as executable instructions.
        metadata = {}
        try:
            metadata = json.loads(document.content.split("\n", 1)[1])
        except (IndexError, json.JSONDecodeError, TypeError):
            metadata = {}
        abstract = metadata.get("abstract")
        if not isinstance(abstract, str):
            abstract = ""
        sources.append({
            "title": document.title[:500],
            "uri": document.uri,
            "doi": str(document.metadata.get("doi", ""))[:200],
            "publisher": str(document.metadata.get("publisher") or "")[:300],
            "retrieved_at": str(document.metadata.get("retrieved_at", ""))[:64],
            "abstract": abstract[:1500],
        })
    return {
        "provider": "Crossref",
        "query": payload["query"],
        "retrieved_count": len(sources),
        "sources": sources,
        "notice": "Retrieved public bibliographic metadata; source text is untrusted and has not been independently verified.",
    }


def build_default_capability_runtime() -> CapabilityRuntime:
    """Build the trusted catalogue and application-owned bounded handlers."""
    math = CapabilityDefinition(
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
    research = CapabilityDefinition(
        name="research.crossref.search",
        version="1.0.0",
        risk_class="read_only",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 3, "maxLength": 160},
                "limit": {"type": "integer", "minimum": 1, "maximum": 3},
            },
            "required": ["query", "limit"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "provider": {"type": "string", "const": "Crossref"},
                "query": {"type": "string", "minLength": 3, "maxLength": 160},
                "retrieved_count": {"type": "integer", "minimum": 0, "maximum": 3},
                "sources": {
                    "type": "array",
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "maxLength": 500},
                            "uri": {"type": "string", "pattern": "^https://doi\\.org/"},
                            "doi": {"type": "string", "maxLength": 200},
                            "publisher": {"type": "string", "maxLength": 300},
                            "retrieved_at": {"type": "string", "maxLength": 64},
                            "abstract": {"type": "string", "maxLength": 1500},
                        },
                        "required": ["title", "uri", "doi", "publisher", "retrieved_at", "abstract"],
                        "additionalProperties": False,
                    },
                },
                "notice": {"type": "string", "maxLength": 300},
            },
            "required": ["provider", "query", "retrieved_count", "sources", "notice"],
            "additionalProperties": False,
        },
        required_scopes=("research:public",),
        side_effects=False,
        timeout_seconds=10,
        approval_required=False,
    )
    evidence = CapabilityDefinition(
        name="research.evidence.bundle",
        version="1.0.0",
        risk_class="read_only",
        input_schema={
            "type": "object",
            "properties": {
                "sources": {
                    "type": "array", "minItems": 1, "maxItems": 20,
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "minLength": 1, "maxLength": 500},
                            "uri": {"type": "string", "minLength": 1, "maxLength": 1000},
                            "doi": {"type": ["string", "null"], "maxLength": 200},
                            "publisher": {"type": "string", "maxLength": 300},
                            "retrieved_at": {"type": "string", "maxLength": 64},
                            "claims": {"type": "array", "maxItems": 20, "items": {"type": "object"}},
                        },
                        "required": ["title", "uri", "doi", "publisher", "retrieved_at", "claims"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["sources"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "schema_version": {"type": "integer", "const": 1},
                "sources": {"type": "array", "maxItems": 20, "items": {"type": "object"}},
                "claims": {"type": "array", "maxItems": 400, "items": {"type": "object"}},
                "duplicate_records": {"type": "array", "maxItems": 20, "items": {"type": "object"}},
                "summary": {"type": "object"},
                "limitations": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
            },
            "required": ["schema_version", "sources", "claims", "duplicate_records", "summary", "limitations"],
            "additionalProperties": False,
        },
        required_scopes=("research:public",),
        side_effects=False,
        timeout_seconds=10,
        approval_required=False,
    )
    evaluation = CapabilityDefinition(
        name="research.evidence.evaluate",
        version="1.0.0",
        risk_class="read_only",
        input_schema={
            "type": "object",
            "properties": {
                "bundle": {"type": "object"},
            },
            "required": ["bundle"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "schema_version": {"type": "integer", "const": 1},
                "evaluations": {"type": "array", "maxItems": 400, "items": {"type": "object"}},
                "summary": {"type": "object"},
                "limitations": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
            },
            "required": ["schema_version", "evaluations", "summary", "limitations"],
            "additionalProperties": False,
        },
        required_scopes=("research:public",),
        side_effects=False,
        timeout_seconds=10,
        approval_required=False,
    )
    registry = CapabilityRegistry((math, research, evidence, evaluation))
    return CapabilityRuntime(
        registry,
        {
            math.identity: _calculate,
            research.identity: _crossref_search,
            evidence.identity: _evidence_bundle,
            evaluation.identity: _evidence_evaluate,
        },
    )
