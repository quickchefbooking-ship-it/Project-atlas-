import httpx
import pytest

from atlas_engine.conversation_contract import (
    ConversationInput,
    ConversationMessage,
)
from atlas_engine.openai_compatible_provider import (
    OpenAICompatibleConfig,
    OpenAICompatibleConversationProvider,
    ReasoningProviderError,
    load_provider_from_environment,
)


def sample_conversation():
    return ConversationInput(
        conversation_id="conversation-1",
        user_id="tenant-user-1",
        messages=(
            ConversationMessage("user", "Hello Professor"),
        ),
    )


def test_provider_is_disabled_by_default():
    assert load_provider_from_environment({}) is None
    assert load_provider_from_environment({"ATLAS_LLM_PROVIDER": "off"}) is None


def test_explicit_provider_configuration_requires_endpoint_and_model():
    with pytest.raises(ValueError, match="URL and model"):
        load_provider_from_environment({"ATLAS_LLM_PROVIDER": "openai_compatible"})


def test_unknown_provider_fails_closed():
    with pytest.raises(ValueError, match="must be 'off'"):
        load_provider_from_environment({"ATLAS_LLM_PROVIDER": "unknown"})


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/v1/chat/completions",
        "http://192.0.2.10/v1/chat/completions",
        "https://user:pass@example.com/v1/chat/completions",
        "https://example.com/v1/chat/completions?debug=true",
    ],
)
def test_provider_rejects_unsafe_endpoint_urls(url):
    with pytest.raises(ValueError):
        OpenAICompatibleConfig(endpoint_url=url, model="local-model")


def test_provider_rejects_non_loopback_plain_http_but_allows_localhost():
    config = OpenAICompatibleConfig(
        endpoint_url="http://127.0.0.1:11434/v1/chat/completions",
        model="local-model",
    )
    assert config.model == "local-model"


def test_provider_sends_bounded_text_only_request_and_returns_provenance():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "model": "served-model-v2",
                "choices": [{"message": {"content": "Hello. I am Professor."}}],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleConversationProvider(
        OpenAICompatibleConfig(
            endpoint_url="https://inference.example.test/v1/chat/completions",
            model="configured-model",
            api_key="test-key",
        ),
        client=client,
    )

    result = provider.respond(sample_conversation())

    assert result.text == "Hello. I am Professor."
    assert result.provider == "openai-compatible"
    assert result.model == "served-model-v2"
    assert seen["headers"]["authorization"] == "Bearer test-key"
    assert '"stream":false' in seen["body"]
    assert '"tools"' not in seen["body"]
    assert seen["url"] == "https://inference.example.test/v1/chat/completions"
    client.close()


def test_provider_rejects_oversized_response_body():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"x" * 2048)
        )
    )
    provider = OpenAICompatibleConversationProvider(
        OpenAICompatibleConfig(
            endpoint_url="https://inference.example.test/v1/chat/completions",
            model="configured-model",
            max_response_chars=256,
            max_response_bytes=1024,
        ),
        client=client,
    )

    with pytest.raises(ReasoningProviderError, match="size limit"):
        provider.respond(sample_conversation())
    client.close()


def test_provider_rejects_oversized_answer_text():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"choices": [{"message": {"content": "a" * 300}}]},
            )
        )
    )
    provider = OpenAICompatibleConversationProvider(
        OpenAICompatibleConfig(
            endpoint_url="https://inference.example.test/v1/chat/completions",
            model="configured-model",
            max_response_chars=256,
            max_response_bytes=2048,
        ),
        client=client,
    )

    with pytest.raises(ReasoningProviderError, match="character limit"):
        provider.respond(sample_conversation())
    client.close()


def test_provider_sanitises_transport_errors():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(502, text="secret upstream diagnostic")
        )
    )
    provider = OpenAICompatibleConversationProvider(
        OpenAICompatibleConfig(
            endpoint_url="https://inference.example.test/v1/chat/completions",
            model="configured-model",
        ),
        client=client,
    )

    with pytest.raises(ReasoningProviderError, match="request failed") as error:
        provider.respond(sample_conversation())
    assert "secret upstream diagnostic" not in str(error.value)
    client.close()


def test_environment_configuration_is_opt_in_and_bounded():
    config = load_provider_from_environment(
        {
            "ATLAS_LLM_PROVIDER": "openai_compatible",
            "ATLAS_LLM_CHAT_COMPLETIONS_URL": "http://localhost:11434/v1/chat/completions",
            "ATLAS_LLM_MODEL": "local-model",
            "ATLAS_LLM_TIMEOUT_SECONDS": "12",
            "ATLAS_LLM_MAX_RESPONSE_CHARS": "8000",
        }
    )

    assert config is not None
    assert config.model == "local-model"
    assert config.timeout_seconds == 12
    assert config.max_response_chars == 8000
    assert config.api_key is None
