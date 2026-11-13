import pytest

from atlas_engine import improvement


def _fake_proposal_store(monkeypatch):
    proposal = {"id": "proposal-test", "status": "pending"}
    updates = []

    def get_proposal(proposal_id):
        return dict(proposal) if proposal_id == proposal["id"] else None

    def update_proposal_status(proposal_id, status, approved_by=None):
        updates.append((proposal_id, status, approved_by))
        proposal["status"] = status
        proposal["approved_by"] = approved_by

    monkeypatch.setattr(improvement, "get_proposal", get_proposal)
    monkeypatch.setattr(improvement, "update_proposal_status", update_proposal_status)
    return proposal, updates


def test_proposal_cannot_be_marked_tested_without_a_real_test_runner(monkeypatch):
    proposal, updates = _fake_proposal_store(monkeypatch)

    with pytest.raises(NotImplementedError, match="not implemented"):
        improvement.ImprovementManager.review_proposal(proposal["id"], "test", "Human reviewer")

    assert proposal["status"] == "pending"
    assert updates == []


def test_proposal_can_only_be_reviewed_once(monkeypatch):
    proposal, updates = _fake_proposal_store(monkeypatch)

    reviewed = improvement.ImprovementManager.review_proposal(
        proposal["id"], "approve", "Human reviewer"
    )

    assert reviewed["status"] == "approved"
    assert updates == [(proposal["id"], "approved", "Human reviewer")]
    with pytest.raises(ValueError, match="Only pending"):
        improvement.ImprovementManager.review_proposal(
            proposal["id"], "reject", "Human reviewer"
        )


def test_automated_identity_labels_cannot_approve_proposals(monkeypatch):
    proposal, updates = _fake_proposal_store(monkeypatch)

    with pytest.raises(PermissionError):
        improvement.ImprovementManager.review_proposal(proposal["id"], "approve", " AI ")

    assert proposal["status"] == "pending"
    assert updates == []
