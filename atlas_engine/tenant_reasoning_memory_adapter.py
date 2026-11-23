"""Connect tenant-scoped approved memory to Professor's bounded reasoning pipeline.

The adapter is deliberately explicit: the verified tenant memory repository
performs authorization, approval, expiry and supersession filtering. Only the
small reference-data shape accepted by the pipeline is forwarded.
"""
from __future__ import annotations

from .cognitive_kernel import CognitiveRequest
from .conversation_contract import ConversationMessage
from .professor_reasoning_pipeline import ProfessorReasoningPipeline
from .tenant_professor_memory import TenantProfessorMemoryRepository


def run_with_tenant_memory(
    pipeline: ProfessorReasoningPipeline,
    memory: TenantProfessorMemoryRepository,
    request: CognitiveRequest,
    *,
    retrieve_evidence: bool = True,
    conversation_history: tuple[ConversationMessage, ...] = (),
    memory_limit: int = 5,
):
    """Retrieve only approved, live owner memories and pass them as reference data."""
    if not isinstance(pipeline, ProfessorReasoningPipeline):
        raise TypeError("A ProfessorReasoningPipeline is required.")
    if not isinstance(memory, TenantProfessorMemoryRepository):
        raise TypeError("A tenant-scoped Professor memory repository is required.")
    if not isinstance(request, CognitiveRequest):
        raise TypeError("A CognitiveRequest is required.")
    if isinstance(memory_limit, bool) or not isinstance(memory_limit, int) or not 1 <= memory_limit <= 5:
        raise ValueError("memory_limit must be between 1 and 5.")

    query = request.task
    if request.context:
        query += "\n" + request.context
    retrieved = memory.retrieve(query, limit=memory_limit)
    approved_memory = tuple({
        "proposal_id": item["proposal_id"],
        "category": item["category"],
        "title": item["title"],
        "content": item["content"],
        "matched_terms": item.get("matched_terms", []),
        "matched_fields": item.get("matched_fields", []),
    } for item in retrieved)

    return pipeline.run(
        request,
        retrieve_evidence=retrieve_evidence,
        approved_memory=approved_memory,
        conversation_history=conversation_history,
    )
