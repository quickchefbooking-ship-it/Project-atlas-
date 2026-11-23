

def test_pipeline_preserves_conflicting_approved_memories_in_both_reasoning_passes():
    provider = TwoPassProvider(
        answer="The saved memories conflict. One says Hey Atlas; the other says Atlas. I need confirmation before treating either as the current preference."
    )
    approved = (
        {
            "proposal_id": "wake-phrase-a",
            "category": "interface",
            "title": "Wake phrase",
            "content": "Use Hey Atlas as the activation phrase.",
            "matched_terms": ["wake", "phrase"],
            "matched_fields": ["title"],
        },
        {
            "proposal_id": "wake-phrase-b",
            "category": "interface",
            "title": "Wake phrase",
            "content": "Use Atlas as the activation phrase.",
            "matched_terms": ["wake", "phrase"],
            "matched_fields": ["title"],
        },
    )
    result = ProfessorReasoningPipeline(provider).run(
        CognitiveRequest(task="What wake phrase should I use?"),
        retrieve_evidence=False,
        approved_memory=approved,
    )
    assert result.status in {"ready", "held_for_review"}
    assert result.memory_proposal_ids == ("wake-phrase-a", "wake-phrase-b")
    for call in provider.calls:
        prompt = call.messages[0].content
        assert "current explicit user request takes priority" in prompt
        assert "preserve the distinction, state the uncertainty, and ask" in prompt
        assert "Use Hey Atlas as the activation phrase." in prompt
        assert "Use Atlas as the activation phrase." in prompt
