import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from .storage import get_proposal, list_proposals, save_proposal, update_proposal_status


class ImprovementManager:
    @staticmethod
    def create_proposal(task_id: str, problem: str, evidence: Dict[str, Any], proposed_change: str, expected_benefit: str, test_plan: str, created_by: str = "human") -> Dict[str, Any]:
        proposal_id = f"proposal-{uuid.uuid4().hex}"
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
        approver = approved_by.strip() if isinstance(approved_by, str) else ""
        if not approver or approver.lower() in {"system", "ai", "auto"}:
            raise PermissionError(
                "An explicit approver label is required. The label is audit metadata, not verified identity."
            )

        if action == "test":
            raise NotImplementedError(
                "Proposal testing is not implemented. A proposal cannot be marked tested without verified test evidence."
            )
        if action not in {"approve", "reject"}:
            raise ValueError("Action must be approve or reject")

        proposal = get_proposal(proposal_id)
        if proposal is None:
            raise ValueError(f"Proposal {proposal_id} not found")
        if proposal.get("status") != "pending":
            raise ValueError("Only pending proposals can be reviewed")

        status = "approved" if action == "approve" else "rejected"
        if not update_proposal_status(proposal_id, status, approver):
            raise ValueError("Proposal was reviewed concurrently or is no longer pending")
        reviewed = get_proposal(proposal_id)
        if reviewed is None:
            raise ValueError(f"Proposal {proposal_id} not found after review")
        return reviewed

    @staticmethod
    def check_production_gate(proposal_id: str) -> Dict[str, Any]:
        proposal = get_proposal(proposal_id)
        if proposal is None:
            raise ValueError(f"Proposal {proposal_id} not found")
        if proposal["status"] != "approved":
            return {"allowed": False, "reason": "Production changes require explicit human approval."}
        return {
            "allowed": True,
            "reason": "Approved for controlled change review only; this does not authorize deployment.",
        }

    @staticmethod
    def list_proposals(limit: int = 20) -> List[Dict[str, Any]]:
        return list_proposals(limit)
