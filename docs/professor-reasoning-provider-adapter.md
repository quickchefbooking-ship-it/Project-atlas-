# Professor reasoning provider adapter

**Status: implemented as an opt-in transport boundary; not enabled or deployed.**

The existing conversation contract and `ConversationService` define a provider-neutral, text-only reasoning seam. This adapter adds a bounded OpenAI-compatible Chat Completions transport for deployments that deliberately choose a compatible inference endpoint.

## Default behaviour

The provider is disabled unless the deployment explicitly sets:

- `ATLAS_LLM_PROVIDER=openai_compatible`
- `ATLAS_LLM_CHAT_COMPLETIONS_URL` to the exact deployment-owned Chat Completions URL
- `ATLAS_LLM_MODEL` to the configured model identifier

Optional settings:

- `ATLAS_LLM_API_KEY`: provider credential; optional for a protected self-hosted endpoint
- `ATLAS_LLM_TIMEOUT_SECONDS`: 1–60 seconds; default 20
- `ATLAS_LLM_MAX_RESPONSE_CHARS`: 256–24,000; default 12,000

When `ATLAS_LLM_PROVIDER` is absent or `off`, configuration returns no provider. Unknown provider names and incomplete explicit configurations fail closed.

## Transport safeguards

- Deployment-owned endpoint only; no endpoint is accepted from a conversation or user request.
- HTTPS is required except for HTTP loopback endpoints (`localhost` or loopback IP).
- Endpoint URLs containing user information, query strings or fragments are rejected.
- Environment proxy settings are not inherited by the HTTP client.
- Connect/read/write/pool timeouts use the configured bounded timeout.
- Request and response byte limits are checked.
- Response text has a separate character limit.
- Provider errors and upstream response bodies are not reflected to the caller.
- Only text messages are sent. Tool/function calling and streaming are not requested or supported.
- The returned provider and model identifiers are retained as provenance.
- The adapter does not store conversation content, invoke capabilities or perform external actions.

## Explicitly not done

- No provider has been selected for the live Professor deployment.
- No paid provider, account, API key or inference service has been configured.
- No secrets or environment variables have been added to hosting.
- The adapter is not wired into the public conversation route. The existing route remains fail-closed until authenticated conversation ownership, persistence, rate limits and a deliberate provider enablement decision are completed.
- No merge or production deployment has occurred.

## Validation

The adapter tests use an in-process HTTPX mock transport. They do not contact a real model or external network. They cover default-off configuration, unsafe URL rejection, request shape, provenance, response bounds and sanitised transport errors.

A self-hosted OpenAI-compatible endpoint is a possible no-provider-fee option, but it still requires compute, secure hosting, model licensing review, operational monitoring and performance testing. "Free software" does not mean free inference infrastructure.
