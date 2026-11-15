"""Opt-in OpenAI-compatible text reasoning transport for Professor.

The adapter is deliberately inert unless ATLAS_LLM_PROVIDER=openai_compatible
and a deployment-owned endpoint/model are configured. It exposes no tools,
function calling, browsing, credentials beyond one optional provider key, or
external actions. Use a self-hosted endpoint for a no-paid-provider deployment.
"""
from __future__ import annotations

import ipaddress
import json
import math
import os
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit

import httpx

from .conversation_contract import ConversationInput, ConversationOutput


class ReasoningProviderError(RuntimeError):
    """A bounded provider request failed or returned an invalid response."""


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    endpoint_url: str
    model: str
    api_key: str | None = None
    provider_name: str = "openai-compatible"
    timeout_seconds: float = 20.0
    max_response_chars: int = 12_000
    max_response_bytes: int = 64_000
    max_request_bytes: int = 32_000

    def __post_init__(self) -> None:
        parsed = urlsplit(self.endpoint_url)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Provider endpoint must be an HTTPS URL or loopback HTTP URL.")
        if parsed.scheme == "http":
            host = parsed.hostname.lower()
            is_loopback_name = host == "localhost"
            try:
                is_loopback_ip = ipaddress.ip_address(host).is_loopback
            except ValueError:
                is_loopback_ip = False
            if not (is_loopback_name or is_loopback_ip):
                raise ValueError("Unencrypted provider endpoints are permitted only on loopback.")
        if not self.model.strip() or len(self.model) > 128:
            raise ValueError("A bounded provider model identifier is required.")
        if not self.provider_name.strip() or len(self.provider_name) > 64:
            raise ValueError("A bounded provider name is required.")
        if not math.isfinite(self.timeout_seconds) or not 1 <= self.timeout_seconds <= 60:
            raise ValueError("Provider timeout must be between 1 and 60 seconds.")
        if not 256 <= self.max_response_chars <= 24_000:
            raise ValueError("Provider response limit must be between 256 and 24000 characters.")
        if not self.max_response_chars <= self.max_response_bytes <= 96_000:
            raise ValueError("Provider response byte limit is invalid.")
        if not 1_024 <= self.max_request_bytes <= 64_000:
            raise ValueError("Provider request byte limit is invalid.")


def load_provider_from_environment(
    environ: Mapping[str, str] | None = None,
) -> OpenAICompatibleConfig | None:
    """Return no provider by default; invalid explicit configuration fails closed."""
    values = os.environ if environ is None else environ
    selected = values.get("ATLAS_LLM_PROVIDER", "off").strip().lower()
    if selected in {"", "off", "disabled", "none"}:
        return None
    if selected != "openai_compatible":
        raise ValueError("ATLAS_LLM_PROVIDER must be 'off' or 'openai_compatible'.")
    endpoint = values.get("ATLAS_LLM_CHAT_COMPLETIONS_URL", "").strip()
    model = values.get("ATLAS_LLM_MODEL", "").strip()
    if not endpoint or not model:
        raise ValueError("Provider URL and model must be configured before enabling reasoning.")
    try:
        timeout = float(values.get("ATLAS_LLM_TIMEOUT_SECONDS", "20"))
        response_chars = int(values.get("ATLAS_LLM_MAX_RESPONSE_CHARS", "12000"))
    except (TypeError, ValueError):
        raise ValueError("Provider timeout and response limit must be valid numbers.") from None
    return OpenAICompatibleConfig(
        endpoint_url=endpoint,
        model=model,
        api_key=values.get("ATLAS_LLM_API_KEY") or None,
        timeout_seconds=timeout,
        max_response_chars=response_chars,
    )


class OpenAICompatibleConversationProvider:
    """Synchronous, bounded Chat Completions transport with no tool support."""

    name = "openai-compatible"

    def __init__(self, config: OpenAICompatibleConfig, client: httpx.Client | None = None):
        self.config = config
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(config.timeout_seconds),
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
            trust_env=False,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def respond(self, conversation: ConversationInput) -> ConversationOutput:
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in conversation.messages
            ],
            "stream": False,
        }
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > self.config.max_request_bytes:
            raise ReasoningProviderError("Conversation exceeds the configured provider request limit.")

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = "Bearer " + self.config.api_key

        try:
            chunks: list[bytes] = []
            total = 0
            with self._client.stream(
                "POST",
                self.config.endpoint_url,
                headers=headers,
                content=encoded,
            ) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > self.config.max_response_bytes:
                        raise ReasoningProviderError("Provider response exceeded the configured size limit.")
                    chunks.append(chunk)
            data = json.loads(b"".join(chunks))
        except ReasoningProviderError:
            raise
        except (httpx.HTTPError, json.JSONDecodeError, UnicodeDecodeError):
            raise ReasoningProviderError("The reasoning provider request failed.") from None

        try:
            actual_model = data.get("model") or self.config.model
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError
            if len(content) > self.config.max_response_chars:
                raise ReasoningProviderError("Provider answer exceeded the configured character limit.")
            if not isinstance(actual_model, str) or not actual_model.strip() or len(actual_model) > 128:
                raise ValueError
        except ReasoningProviderError:
            raise
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            raise ReasoningProviderError("The reasoning provider returned an invalid response.") from None

        return ConversationOutput(
            text=content,
            provider=self.config.provider_name,
            model=actual_model,
        )
