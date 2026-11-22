"""Provider-neutral conversation contracts for Professor.

This module defines the safe boundary between the orchestration core and a
future language-model provider. It performs no network calls and grants no
tool or external-system access.
"""
from dataclasses import dataclass
from typing import Literal, Protocol, Sequence, runtime_checkable

Role = Literal["system", "user", "assistant"]
MAX_MESSAGE_CHARS = 4_000
MAX_TURNS = 24
# Pipeline messages reserve one system prompt and the latest user turn.
MAX_HISTORY_MESSAGES = MAX_TURNS - 2
MAX_CONTEXT_CHARS = 24_000


@dataclass(frozen=True)
class ConversationMessage:
    role: Role
    content: str

    def __post_init__(self) -> None:
        if self.role not in ("system", "user", "assistant"):
            raise ValueError("Unsupported conversation role")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("Conversation message content must not be blank")
        if len(self.content) > MAX_MESSAGE_CHARS:
            raise ValueError("Conversation message exceeds the character limit")


@dataclass(frozen=True)
class ConversationInput:
    conversation_id: str
    user_id: str
    messages: tuple[ConversationMessage, ...]
    locale: str = "en-GB"

    def __post_init__(self) -> None:
        if not self.conversation_id.strip() or not self.user_id.strip():
            raise ValueError("Conversation and user identifiers are required")
        if not self.messages or len(self.messages) > MAX_TURNS:
            raise ValueError("Conversation must contain between 1 and 24 messages")
        if self.messages[-1].role != "user":
            raise ValueError("The final conversation message must be from the user")
        if sum(len(message.content) for message in self.messages) > MAX_CONTEXT_CHARS:
            raise ValueError("Conversation context exceeds the character budget")
        if not self.locale or len(self.locale) > 32:
            raise ValueError("Locale must be a non-empty short language tag")


@dataclass(frozen=True)
class ConversationOutput:
    text: str
    provider: str
    model: str
    finish_reason: str = "stop"

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("Provider returned an empty assistant response")
        if len(self.text) > MAX_CONTEXT_CHARS:
            raise ValueError("Assistant response exceeds the character limit")
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("Provider and model identifiers are required")


@runtime_checkable
class ConversationProvider(Protocol):
    """A text-only reasoning provider; no tools or side effects are implied."""

    name: str

    def respond(self, conversation: ConversationInput) -> ConversationOutput:
        """Return one assistant response or raise a provider-specific error."""
        ...


def build_conversation_input(
    conversation_id: str,
    user_id: str,
    prior_messages: Sequence[ConversationMessage],
    latest_user_message: str,
    locale: str = "en-GB",
) -> ConversationInput:
    """Append a user turn while retaining only the bounded recent context."""
    latest = ConversationMessage(role="user", content=latest_user_message)
    retained = tuple(prior_messages[-(MAX_TURNS - 1):]) + (latest,)
    while len(retained) > 1 and sum(len(item.content) for item in retained) > MAX_CONTEXT_CHARS:
        retained = retained[1:]
    return ConversationInput(
        conversation_id=conversation_id,
        user_id=user_id,
        messages=retained,
        locale=locale,
    )
