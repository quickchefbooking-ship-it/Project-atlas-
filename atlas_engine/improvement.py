import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from .storage import get_proposal, list_proposals, save_proposal, update_proposal_status


class ImprovementManager:
    @staticmethod
    def create_proposal(task_id: str, problem: str, evidence: Dict[str, Any], proposed_change: str, expected_benefit: str, test_plan: str, created_by: str = "human") -> Dict[str, Any]:
        proposal_id = f"proposal-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        proposal = {
            "id": proposal_id,
            "task_id": task_id,
            "problem": problem,
            "evidence_json": json.dumps(evidence, sort_keys=True),
            "proposed_change": proposed_change,
            "expected_benefit": expected_benefit,
            "test_plan": test_plan,
            "status": "pending",
            "created_by": created_by,
            "approved_by": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        save_proposal(proposal)
        return proposal

    @staticmethod
    def review_proposal(proposal_id: str, action: str, approved_by: str) -> Dict[str, Any]:
        if not approved_by or approved_by.lower() in {"system", "ai", "auto", ""}:
            raise PermissionError("Only a human approver may approve or reject a proposal.")
        if action not in {"approve", "reject", "test"}:
            raise ValueError("Action must be approve, reject or test")

        status = "approved" if action == "approve" else "rejected" if action == "reject" else "tested"
        update_proposal_status(proposal_id, status, approved_by)
        proposal = get_proposal(proposal_id)
        if proposal is None:
            raise ValueError(f"Proposal {proposal_id} not found")
        return proposal

    @staticmethod
    def check_production_gate(proposal_id: str) -> Dict[str, Any]:
        proposal = get_proposal(proposal_id)
        if proposal is None:
            raise ValueError(f"Proposal {proposal_id} not found")
        if proposal["status"] != "approved":
            return {"allowed": False, "reason": "Production changes require explicit human approval."}
        return {"allowed": True, "reason": "Approved for production change review"}

    @staticmethod
    def list_proposals(limit: int = 20) -> List[Dict[str, Any]]:
        return list_proposals(limit)
