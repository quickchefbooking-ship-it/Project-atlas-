---
id: knowledge-rag-integrity-001
title: "Knowledge library integrity: poisoning, embeddings and access boundaries"
division: "security"
topics:
  - data-poisoning
  - knowledge-integrity
  - retrieval-augmented-generation
  - vector-databases
  - access-control
source:
  publisher: "OWASP Gen AI Security Project"
  guidance:
    - title: "LLM04:2025 Data and Model Poisoning"
      url: "https://genai.owasp.org/llmrisk/llm042025-data-and-model-poisoning/"
    - title: "LLM08:2025 Vector and Embedding Weaknesses"
      url: "https://genai.owasp.org/llmrisk/llm082025-vector-and-embedding-weaknesses/"
  retrieved: "2026-11-13"
  source_type: "primary-guidance"
review_status: "curated-reference"
---

# Knowledge library integrity: poisoning, embeddings and access boundaries

## Purpose

This note summarises OWASP Gen AI Security Project guidance on risks to external knowledge stores, retrieval-augmented generation (RAG), embeddings and model data.

## Data and model poisoning

Data poisoning is the manipulation of pre-training, fine-tuning or embedding data to introduce vulnerabilities, backdoors or bias. It can degrade model performance, produce toxic or misleading outputs, or compromise downstream systems. External and unverified sources are a particular risk.

Poisoning can occur at different stages:
- training data can be deliberately manipulated;
- fine-tuning examples can introduce biased or unsafe behaviour;
- embedding and retrieval corpora can be seeded with misleading material;
- user-provided documents may contain malicious or hidden instructions;
- model repositories can contain unsafe serialized artifacts or other supply-chain threats.

## RAG, vector and embedding risks

OWASP identifies several risks for systems that store or retrieve vector representations:
- **Unauthorised access and leakage:** weak access controls can expose personal, proprietary or restricted information.
- **Cross-context leakage:** shared stores can return material belonging to another user, team or tenant.
- **Embedding inversion:** attackers may recover source information from embeddings.
- **Data poisoning:** malicious or unverified records can manipulate retrieval and model responses.
- **Knowledge conflicts:** sources may disagree, or old and new information may be mixed without clear precedence.
- **Behaviour changes:** retrieved material can influence response style and quality as well as factual content.

## Controls for AtlasOnePro

1. **Track provenance and transformations.** Keep source identity, canonical URI, retrieval time, content hash, version and processing history.
2. **Validate before ingestion.** Check source legitimacy, document integrity, hidden content and permitted usage before adding material.
3. **Use explicit review states.** New content is pending and unverified. Only reviewed, approved content enters normal retrieval.
4. **Partition private data.** When multi-user support is introduced, enforce permission-aware storage and tenant boundaries at query time, not merely in the user interface.
5. **Minimise sensitive content.** Do not store secrets or unnecessary personal data. Treat embeddings as potentially sensitive, not anonymous.
6. **Version knowledge.** Preserve update history and identify stale or superseded documents rather than silently overwriting them.
7. **Audit retrieval.** Record which sources and document versions informed an answer, subject to privacy and retention controls.
8. **Test the corpus.** Run adversarial tests for hidden instructions, misleading records, duplicate/contradictory documents and cross-user leakage.
9. **Keep source data separate from instructions.** Retrieved content is evidence, never a policy override or permission grant.
10. **Evaluate groundedness.** Check whether retrieved passages are relevant and whether each material answer claim is supported by them.

## Practical Source Division rules

- Keep original source URLs and content fingerprints.
- Record the source's publication date separately from the retrieval date when known.
- Mark uncertain publication dates as unknown; do not invent them.
- Do not treat a high similarity score as proof of truth.
- Present conflicting evidence and dates to the Professor.
- Keep read-only knowledge retrieval separate from external write capabilities.
- Require human review before promoting unknown-source material.
- Do not load executable model files or code from a source as part of ordinary document ingestion.

## Source records

1. OWASP Gen AI Security Project, LLM04:2025 Data and Model Poisoning: https://genai.owasp.org/llmrisk/llm042025-data-and-model-poisoning/
2. OWASP Gen AI Security Project, LLM08:2025 Vector and Embedding Weaknesses: https://genai.owasp.org/llmrisk/llm082025-vector-and-embedding-weaknesses/

Retrieved 2026-11-13. This file is a concise paraphrased engineering note, not a verbatim reproduction.
