from concurrent.futures import ThreadPoolExecutor

import pytest

from atlas_engine import improvement, storage


def _fake_proposal_store(monkeypatch):
    proposal = {"id": "proposal-test", "status": "pending"}
    updates = []

    def get_proposal(proposal_id):
        return dict(proposal) if proposal_id == proposal["id"] else None

    def update_proposal_status(proposal_id, status, approved_by=None):
        updates.append((proposal_id, status, approved_by))
        proposal["status"] = status
        proposal["approved_by"] = approved_by
        return True

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


def test_review_conflict_is_reported_without_overwriting_the_winner(monkeypatch):
    proposal, updates = _fake_proposal_store(monkeypatch)
    monkeypatch.setattr(improvement, "update_proposal_status", lambda *_args: False)

    with pytest.raises(ValueError, match="reviewed concurrently"):
        improvement.ImprovementManager.review_proposal(
            proposal["id"], "reject", "Second reviewer"
        )

    assert proposal["status"] == "pending"
    assert updates == []


def test_proposal_review_transition_is_atomic_under_concurrent_reviewers(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "proposal-review.db"))
    storage.init_db()
    storage.save_proposal({
        "id": "proposal-race",
        "task_id": None,
        "problem": "Concurrent review test",
        "evidence_json": "{}",
        "proposed_change": "No production change",
        "expected_benefit": "One review winner",
        "test_plan": "Concurrent compare-and-set",
        "status": "pending",
        "created_by": "test",
        "approved_by": None,
        "created_at": storage.now_isoformat(),
    })

    def review(args):
        status, reviewer = args
        return storage.update_proposal_status("proposal-race", status, reviewer)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(review, [
            ("approved", "reviewer-a"),
            ("rejected", "reviewer-b"),
        ]))

    assert sorted(outcomes) == [False, True]
    saved = storage.get_proposal("proposal-race")
    assert saved["status"] in {"approved", "rejected"}
    assert saved["approved_by"] == (
        "reviewer-a" if saved["status"] == "approved" else "reviewer-b"
    )


def test_automated_identity_labels_cannot_approve_proposals(monkeypatch):
    proposal, updates = _fake_proposal_store(monkeypatch)

    with pytest.raises(PermissionError):
        improvement.ImprovementManager.review_proposal(proposal["id"], "approve", " AI ")

    assert proposal["status"] == "pending"
    assert updates == []
