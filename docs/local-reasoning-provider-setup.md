# Local Professor reasoning provider (self-hosted-first)

This guide configures THE PROFESSOR to use a locally hosted OpenAI-compatible text model without signing up for a paid hosted AI API.

## What this does — and does not do

- Uses the existing bounded `OpenAICompatibleConversationProvider`; it does not add another provider implementation.
- Sends text-only Chat Completions requests. Tool/function calling, browsing and external actions are not enabled.
- Keeps the provider disabled until `ATLAS_LLM_PROVIDER=openai_compatible` is explicitly set.
- Allows plain HTTP only for loopback addresses (`localhost`, `127.0.0.1`, or IPv6 loopback). Non-loopback endpoints must use HTTPS.
- Does not make a local model available on an iPhone by itself. The model runs on the machine hosting the Atlas application; the iPhone browser connects to Atlas, not directly to the model.

A self-hosted model has no per-token API fee, but it still needs suitable RAM/VRAM, disk space, electricity and an initial model download. Performance depends on the hardware and model size.

## Local Ollama example

1. Install Ollama on the same computer that will run the Atlas application, using the official Ollama installer for that operating system.
2. Start the Ollama service.
3. Download a model that the computer can run. For example, use Ollama's model library to choose a small instruct/chat model appropriate to the available memory, then run:

   ```sh
   ollama pull <your-model-name>
   ```

4. Confirm the exact installed model name:

   ```sh
   ollama list
   ```

5. Confirm the OpenAI-compatible endpoint is available locally. Ollama's compatible Chat Completions endpoint is:

   ```text
   http://127.0.0.1:11434/v1/chat/completions
   ```

6. Copy `.env.example` to `.env` if you have not already. Set the following values, replacing the model placeholder with the exact name shown by `ollama list`:

   ```dotenv
   ATLAS_LLM_PROVIDER=openai_compatible
   ATLAS_LLM_CHAT_COMPLETIONS_URL=http://127.0.0.1:11434/v1/chat/completions
   ATLAS_LLM_MODEL=<your-exact-local-model-name>
   ATLAS_LLM_TIMEOUT_SECONDS=30
   ATLAS_LLM_MAX_RESPONSE_CHARS=12000
   ATLAS_LLM_API_KEY=
   ```

7. Restart the Atlas application so it reads the environment. Check `GET /launch/readiness`: `reasoning_provider_configured` should become true. This reports configuration presence only; it does not prove the model can complete a real request.
8. After the verified identity boundary is configured, sign in through the approved identity flow and test a short, harmless conversation. Confirm that Professor returns a real model response and that a follow-up turn retains context. Record the result before treating the provider as live.

## Important network boundary

The loopback URL works only when Ollama and the Atlas application run on the same host. If Atlas is running on a remote hosted service, `127.0.0.1` means that remote host, not your iPhone or home computer. Do not expose Ollama's unauthenticated port to the public internet and do not use an unencrypted non-loopback URL. A separate-host setup needs a deliberately secured HTTPS endpoint, firewall restrictions, authentication and an operational review; that is not configured by this guide.

## Fail-closed and rollback

- To turn reasoning off, set `ATLAS_LLM_PROVIDER=off` (or remove the setting) and restart Atlas.
- Do not add provider keys or credentials to Git, browser storage, URLs or chat messages.
- Do not set a paid provider or enable `ATLAS_ENABLE_PAID_AI` as part of this local setup.
- The provider has bounded request/response sizes and timeouts. It has no tools and cannot execute a plan.
- A configured provider is not a verified release. Keep live-provider round-trip verification and hosted sign-in as separate release gates.

## Current limitations

This is text reasoning, not a guarantee of human-level reasoning. Model quality, speed and context capacity depend on the chosen local model and hardware. The browser voice page uses the device's speech recognition and speech synthesis; it is not a continuous, always-listening wake-word system.
