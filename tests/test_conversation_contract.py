import pytest

from atlas_engine.conversation_contract import (
    ConversationInput,
    ConversationMessage,
    ConversationOutput,
    MAX_CONTEXT_CHARS,
    build_conversation_input,
)


def test_conversation_requires_user_final_turn():
    with pytest.raises(ValueError, match="final conversation message"):
        ConversationInput(
            conversation_id="c1",
            user_id="u1",
            messages=(ConversationMessage("assistant", "Hello"),),
        )


def test_conversation_rejects_oversized_context():
    messages = tuple(
        ConversationMessage("user" if index % 2 == 0 else "assistant", "x" * 3_500)
        for index in range(7)
    )
    with pytest.raises(ValueError, match="context exceeds"):
        ConversationInput(
            conversation_id="c1",
            user_id="u1",
            messages=messages,
        )


def test_context_builder_appends_latest_user_turn_and_bounds_history():
    history = (
        ConversationMessage("user", "Earlier question"),
        ConversationMessage("assistant", "Earlier answer"),
    )
    result = build_conversation_input("c1", "u1", history, "What next?")
    assert result.messages[-1] == ConversationMessage("user", "What next?")
    assert len(result.messages) == 3
    assert result.locale == "en-GB"


def test_context_builder_discards_oldest_messages_to_fit_budget():
    history = tuple(
        ConversationMessage("user" if index % 2 == 0 else "assistant", "x" * 3_500)
        for index in range(7)
    )
    result = build_conversation_input("c1", "u1", history, "latest")
    assert result.messages[-1] == ConversationMessage("user", "latest")
    assert len(result.messages) < len(history) + 1
    assert sum(len(item.content) for item in result.messages) <= MAX_CONTEXT_CHARS


def test_provider_output_requires_real_text_and_identity():
    with pytest.raises(ValueError, match="empty assistant response"):
        ConversationOutput(text=" ", provider="local", model="test")
    with pytest.raises(ValueError, match="identifiers"):
        ConversationOutput(text="Hello", provider="", model="test")
