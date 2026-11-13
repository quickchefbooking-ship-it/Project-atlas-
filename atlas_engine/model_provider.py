"""Model-provider contracts for Professor.

Providers supply reasoning output only. They do not execute tools, grant permissions,
persist memory, or control task lifecycle. External provider adapters are deliberately
not implemented in this module.
"""
from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_PROMPT_CHARS = 24_000
MAX_OUTPUT_CHARS = 24_000
MAX_METADATA_CHARS = 4_000
MAX_DETERMINISTIC_LATENCY_MS = 30_000


class ProviderError(RuntimeError):
    """Safe, provider-neutral failure without request content or credentials."""


class ProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    system_instruction: str = Field(min_length=1, max_length=8_000)
    task_input: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    output_format: Literal["text", "json"] = "json"
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    max_output_tokens: int = Field(default=2_000, ge=1, le=8_000)
    correlation_id: str = Field(min_length=1, max_length=128)

    @field_validator("system_instruction", "task_input", "correlation_id")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Provider request fields must not be blank.")
        return value


class ProposedCapabilityCall(BaseModel):
    """A proposal for the orchestrator to validate; never an executable command."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    capability_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$")
    capability_version: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    provider_id: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=128)
    adapter_version: str = Field(min_length=1, max_length=64)
    output_text: str = Field(max_length=MAX_OUTPUT_CHARS)
    proposed_capability_calls: list[ProposedCapabilityCall] = Field(default_factory=list, max_length=12)
    usage: dict[str, int] = Field(default_factory=dict)
    latency_ms: int = Field(ge=0, le=MAX_DETERMINISTIC_LATENCY_MS)
    request_id: str = Field(min_length=1, max_length=128)
    output_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ProviderDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    provider_id: str
    model_id: str
    adapter_version: str
    supports_json_output: bool
    supports_proposed_tool_calls: bool
    external_network: bool
    paid_service: bool


class ModelProvider(ABC):
    """Minimal provider contract. Implementations must be bounded and side-effect free."""

    @abstractmethod
    def describe(self) -> ProviderDescriptor:
        raise NotImplementedError

    @abstractmethod
    def generate(self, request: ProviderRequest, *, timeout_seconds: float) -> ProviderResponse:
        raise NotImplementedError


class DeterministicMockProvider(ModelProvider):
    """Repeatable fixture provider for tests; not an AI model and not production intelligence."""

    PROVIDER_ID = "deterministic_mock"
    MODEL_ID = "fixture-v1"
    ADAPTER_VERSION = "1.0.0"

    def __init__(self, response_text: str = '{"status":"mock","message":"No model inference performed."}'):
        if not isinstance(response_text, str) or len(response_text) > MAX_OUTPUT_CHARS:
            raise ValueError("Mock response exceeds the permitted output size.")
        self._response_text = response_text

    def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id=self.PROVIDER_ID,
            model_id=self.MODEL_ID,
            adapter_version=self.ADAPTER_VERSION,
            supports_json_output=True,
            supports_proposed_tool_calls=True,
            external_network=False,
            paid_service=False,
        )

    def generate(self, request: ProviderRequest, *, timeout_seconds: float = 5.0) -> ProviderResponse:
        if not isinstance(request, ProviderRequest):
            raise TypeError("A validated ProviderRequest is required.")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
            raise ValueError("Timeout must be a positive number of seconds.")
        if timeout_seconds <= 0 or timeout_seconds > 30:
            raise ValueError("Timeout must be greater than zero and at most 30 seconds.")

        started = time.monotonic()
        output = self._response_text
        if request.output_format == "json":
            try:
                parsed = json.loads(output)
            except (TypeError, ValueError) as exc:
                raise ProviderError("Mock provider fixture is not valid JSON.") from exc
            if not isinstance(parsed, (dict, list)):
                raise ProviderError("Mock provider JSON output must be an object or array.")

        elapsed_ms = int((time.monotonic() - started) * 1000)
        if elapsed_ms > timeout_seconds * 1000:
            raise ProviderError("Provider request exceeded its time budget.")

        digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
        return ProviderResponse(
            provider_id=self.PROVIDER_ID,
            model_id=self.MODEL_ID,
            adapter_version=self.ADAPTER_VERSION,
            output_text=output,
            proposed_capability_calls=[],
            usage={"input_characters": len(request.system_instruction) + len(request.task_input),
                   "output_characters": len(output)},
            latency_ms=elapsed_ms,
            request_id=request.correlation_id,
            output_sha256=digest,
        )
