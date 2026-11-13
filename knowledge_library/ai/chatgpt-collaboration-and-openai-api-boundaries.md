---
id: knowledge-openai-chatgpt-001
title: "ChatGPT collaboration and OpenAI API boundaries"
division: "ai"
topics:
  - chatgpt
  - openai-api
  - data-controls
  - function-calling
  - tool-security
source:
  publisher: "OpenAI"
  url: "https://help.openai.com/en/articles/7730893-data-controls-in-chatgpt"
  retrieved: "2026-11-13"
  related:
    - "https://developers.openai.com/api/docs/guides/function-calling"
review_status: "curated-reference"
---

# ChatGPT collaboration and OpenAI API boundaries

## Purpose

ChatGPT can contribute research, analysis, planning and reviewed knowledge notes to AtlasOnePro. It is important to distinguish the ChatGPT product, the underlying model, the OpenAI API and the Professor's own persistent library. They are related, but they are not the same system.

This is a design reference. It does not create a live ChatGPT-to-Professor connection or enable an OpenAI API key.

## ChatGPT as a research collaborator

ChatGPT can help:
- formulate research questions;
- compare and summarise retrieved sources;
- draft structured notes and technical plans;
- identify contradictions, gaps and assumptions;
- produce candidate test cases and review checklists.

ChatGPT output is not automatically authoritative. The Professor must retain supporting source URLs, distinguish quoted facts from inference, check time-sensitive claims and keep unverified outputs pending until reviewed.

The Professor's knowledge library is the durable store. A conversation is not itself a substitute for a versioned knowledge record.

## ChatGPT data controls

OpenAI's [ChatGPT data controls](https://help.openai.com/en/articles/7730893-data-controls-in-chatgpt) describe account controls for model improvement, chat history, temporary chats and data export. Available controls depend on account and workspace settings.

The documentation distinguishes memory/personalisation from model-training controls. Temporary Chat is not shown in normal chat history and does not create or update memories; OpenAI states that it may be retained for up to 30 days for safety purposes. Eligible signed-in users can request a data export through ChatGPT settings or the Privacy Portal.

For AtlasOnePro:
- only import conversations or files that the user is authorised to share;
- minimise personal, confidential and privileged information;
- preserve the conversation/task origin where appropriate;
- do not assume that a ChatGPT conversation is a complete or permanent archive;
- keep exported account data private and access-controlled.

## OpenAI API and function calling

The [OpenAI function-calling guide](https://developers.openai.com/api/docs/guides/function-calling) describes how a model can request that an application call a function. The application supplies tool definitions and schemas; the model may return a tool call; the application validates and executes it; and the tool result is returned to the model.

A model-generated tool call is a request, not permission. The application must independently:
1. validate the function name and argument schema;
2. authenticate the caller;
3. check authorisation and scope;
4. enforce rate, time and resource limits;
5. require action-specific human approval for consequential side effects;
6. execute the capability outside the model;
7. record the request, decision, result and provenance.

Use narrow tool schemas and a fixed allowlist. Do not give the model unrestricted shell, database or account credentials.

## Cost and integration boundary

A ChatGPT subscription does not itself mean that AtlasOnePro has an OpenAI API connection or prepaid API usage. API access and billing are separate and must be checked independently.

The Professor prototype keeps paid AI disabled by default. Do not add API credentials, enable paid inference, or create a new paid integration without explicit approval. The local knowledge library and retrieval system should remain useful without a paid model API.

## What cannot be copied into the library

The library can store approved conversation outputs, research notes, user-supplied documents and public documentation. It cannot export or reproduce the underlying proprietary model weights or the full private training corpus from ChatGPT. Retrieval from the library is not the same as training or fine-tuning a model.

## Source records

- OpenAI Help Center, [Data controls in ChatGPT](https://help.openai.com/en/articles/7730893-data-controls-in-chatgpt)
- OpenAI API documentation, [Function calling](https://developers.openai.com/api/docs/guides/function-calling)

Retrieved 2026-11-13. Check current account controls, API documentation, terms and pricing before enabling any integration.
