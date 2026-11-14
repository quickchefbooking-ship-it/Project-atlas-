import pytest

from atlas_engine.conversation_contract import (
    ConversationInput,
    ConversationMessage,
    ConversationOutput,
)
from atlas_engine.conversation_service import (
    ConversationNotConfigured,
    ConversationService,
)


def sample_input():
    return ConversationInput(
        conversation_id="conversation-1",
        user_id="user-1",
        messages=(ConversationMessage("user", "Hello Professor"),),
    )


class StubProvider:
    name = "test-stub"

    def respond(self, conversation):
        assert conversation.messages[-1].content == "Hello Professor"
        return ConversationOutput(
            text="Hello. How can I help?",
            provider="test-stub",
            model="fixture-v1",
        )


def test_service_fails_closed_without_provider():
    service = ConversationService()
    assert service.is_configured is False
    with pytest.raises(ConversationNotConfigured):
        service.respond(sample_input())


def test_service_calls_only_explicitly_injected_provider():
    service = ConversationService(StubProvider())
    result = service.respond(sample_input())
    assert service.is_configured is True
    assert result.text == "Hello. How can I help?"
    assert result.provider == "test-stub"


def test_service_rejects_provider_returning_untyped_data():
    class InvalidProvider:
        name = "invalid"

        def respond(self, conversation):
            return {"text": "pretend"}

    with pytest.raises(TypeError, match="ConversationOutput"):
        ConversationService(InvalidProvider()).respond(sample_input())
