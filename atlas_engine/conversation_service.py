"""Fail-closed orchestration service for text-only Professor conversations.

A provider is injected explicitly by the application composition root. This
service does not discover providers, make network calls, persist chat history,
invoke tools, or perform external actions.
"""
from __future__ import annotations

from .cognitive_kernel import CognitiveRequest
from .professor_reasoning_pipeline import ProfessorReasoningPipeline, ProfessorReasoningResult

from .conversation_contract import (
    ConversationInput,
    ConversationOutput,
    ConversationProvider,
)


class ConversationNotConfigured(RuntimeError):
    """Raised when no approved reasoning provider has been configured."""


class ConversationService:
    def __init__(self, provider: ConversationProvider | None = None) -> None:
        self._provider = provider

    @property
    def is_configured(self) -> bool:
        return self._provider is not None

    def reason(self, request: CognitiveRequest) -> ProfessorReasoningResult:
        """Run the complete cognitive pipeline through the explicitly injected provider."""
        if self._provider is None:
            raise ConversationNotConfigured(
                "Professor's conversational reasoning service is not configured."
            )
        return ProfessorReasoningPipeline(self._provider).run(request)

    def respond(self, conversation: ConversationInput) -> ConversationOutput:
        if self._provider is None:
            raise ConversationNotConfigured(
                "Professor's conversational reasoning service is not configured."
            )
        result = self._provider.respond(conversation)
        if not isinstance(result, ConversationOutput):
            raise TypeError("Conversation providers must return ConversationOutput.")
        return result
