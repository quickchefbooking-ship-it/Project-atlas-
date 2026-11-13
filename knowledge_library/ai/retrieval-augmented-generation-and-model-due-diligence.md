---
id: knowledge-huggingface-rag-001
title: "Retrieval-augmented generation, tool schemas and model documentation"
division: "ai"
topics:
  - retrieval-augmented-generation
  - grounding
  - model-cards
  - tool-calling
  - model-evaluation
source:
  publisher: "Hugging Face"
  guidance:
    - title: "Expanding Chat Templates with Tools and Documents"
      url: "https://huggingface.co/docs/transformers/main/en/chat_template_tools_and_documents"
    - title: "Model Cards"
      url: "https://huggingface.co/docs/hub/en/model-cards"
  retrieved: "2026-11-13"
  source_type: "official-documentation"
review_status: "curated-reference"
---

# Retrieval-augmented generation, tool schemas and model documentation

## Purpose

This note records practical concepts from Hugging Face's official Transformers and Hub documentation for building a grounded, inspectable assistant. It is a concise paraphrase, not a copy of the documentation.

## Retrieval-augmented generation (RAG)

RAG systems retrieve relevant documents from a corpus before generating an answer. This allows an assistant to consult information outside the model's fixed context or training data. The retrieved documents are supplied as context to the model.

Hugging Face documents a common document shape for chat templates: a list of records containing a title and document contents. However, support for a `documents` argument is not universal. A model's actual chat template and model card must be checked before assuming it supports a particular RAG interface.

### Professor design implications

1. Keep retrieval separate from generation: search the approved library first, then provide selected passages as clearly delimited reference context.
2. Preserve each passage's title, source URI, content hash and review state so the final answer can be traced back to evidence.
3. Do not treat similarity or keyword ranking as proof that a passage is true or relevant.
4. If retrieval returns no suitable evidence, say so rather than inventing a source-backed answer.
5. Evaluate context relevance, answer groundedness and whether the response answers the user's actual question.
6. Keep untrusted source text separate from system instructions and tool permissions. Retrieved text is evidence, not executable instruction.
7. Verify model-specific template support; do not assume every model understands the same document format.

## Tool calling and function schemas

Hugging Face's Transformers documentation describes passing tool definitions to a chat template. The model receives a structured description of available functions and their arguments; application code remains responsible for parsing the model's requested call, validating it, executing the function and returning the result to the conversation.

A robust tool definition should use:
- a descriptive function name;
- type hints for every argument;
- a concise description and argument documentation;
- simple, bounded argument structures.

The application must not blindly execute generated tool calls. It should validate the function name, argument schema, caller permissions and action-specific approval requirements before execution. Tool-call formats can differ between model families, so parsers must be model-aware and tested.

### Professor design implications

- Use a fixed allowlist of callable capabilities.
- Validate arguments against a strict schema before dispatch.
- Enforce least privilege outside the language model.
- Keep read-only research tools distinct from write-capable actions.
- Require explicit human approval for consequential external actions.
- Record tool request, validated arguments, result and provenance in an audit trail.
- Treat tool output as untrusted data when it re-enters the model context.

## Model cards as due-diligence records

Hugging Face describes model cards as repository README documents containing metadata and human-readable information. They help users understand a model and support discovery and reproducibility.

When assessing a candidate model, inspect:
- intended uses and out-of-scope uses;
- known limitations, biases and ethical considerations;
- training parameters and experimental information;
- training datasets and base-model lineage;
- evaluation results and the source of those results;
- declared licence and any custom licence terms;
- task tags, supported library and version information.

A model card is primarily documentation supplied by the model author or repository maintainer. Its claims should be checked against independent evaluations and the intended deployment environment. A leaderboard score or download count alone is not proof of suitability, security or reliability.

## Safe model and dataset selection checklist

Before Professor adopts a model, dataset or Space:
1. identify the canonical repository and owner;
2. read the model/dataset card and licence;
3. inspect intended uses, limitations, training data and evaluation provenance;
4. check base model, dependencies, file types and update history;
5. assess privacy, security, resource requirements and deployment constraints;
6. test on representative tasks and adversarial examples;
7. record the exact repository revision and evaluation conditions;
8. obtain approval before downloading executable artefacts or enabling a new runtime dependency.

## Source records

1. Hugging Face, *Expanding Chat Templates with Tools and Documents*: https://huggingface.co/docs/transformers/main/en/chat_template_tools_and_documents
2. Hugging Face, *Model Cards*: https://huggingface.co/docs/hub/en/model-cards

Retrieved 2026-11-13. This note paraphrases official documentation and should be checked against the linked pages when implementing version-specific behaviour.
