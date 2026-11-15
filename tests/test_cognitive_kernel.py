import pytest

from atlas_engine.cognitive_kernel import (
    ActionBoundary, CognitiveRequest, CognitiveStage, frame_task, review_frame,
)


def test_frames_clear_information_task_without_claiming_execution():
    frame = frame_task(CognitiveRequest(
        task="Explain how a staged reasoning pipeline should work",
        context="AtlasOnePro Professor brain",
        constraints=("Keep it provider-neutral",),
    ))
    assert frame.stage is CognitiveStage.READY_FOR_REASONING
    assert frame.reasoning_ready is True
    assert frame.constraints == ("Keep it provider-neutral",)
    assert frame.action_boundary is ActionBoundary.INFORMATION_ONLY


def test_short_ambiguous_request_requires_clarification():
    frame = frame_task(CognitiveRequest(task="Sort this"))
    assert frame.stage is CognitiveStage.NEEDS_CLARIFICATION
    assert frame.reasoning_ready is False
    assert frame.open_questions == ("What outcome would you like to achieve?",)
    assert "Resolve open questions" in review_frame(frame)[0]


def test_external_side_effect_is_flagged_for_approval():
    frame = frame_task(CognitiveRequest(task="Send the final proposal to the customer"))
    assert frame.action_boundary is ActionBoundary.HUMAN_APPROVAL_REQUIRED
    assert any("verified human approval" in item for item in review_frame(frame))


def test_drafting_is_not_permission_to_send():
    frame = frame_task(CognitiveRequest(task="Draft an email to the customer"))
    assert frame.action_boundary is ActionBoundary.DRAFT_ONLY
    assert any("draft form" in item for item in review_frame(frame))


def test_missing_context_is_reported_not_invented():
    frame = frame_task(CognitiveRequest(task="Compare the two proposals"))
    assert frame.context == ""
    assert frame.assumptions == (
        "No additional background context was supplied.",
        "No explicit constraints were supplied.",
    )
    assert any("missing context" in item for item in review_frame(frame))


def test_invalid_or_unbounded_inputs_are_rejected():
    with pytest.raises(ValueError):
        CognitiveRequest(task=" ")
    with pytest.raises(ValueError):
        CognitiveRequest(task="x" * 4001)
    with pytest.raises(ValueError):
        CognitiveRequest(task="Review this", constraints=("x",) * 25)
