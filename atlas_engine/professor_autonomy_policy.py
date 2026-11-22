"""Fail-closed policy for Professor's staged autonomous work modes.

This policy describes what an autonomous worker may attempt. It is not an
identity provider, approval system, sandbox implementation or deployment
mechanism. Callers must still enforce verified identity, tenant scopes,
resource limits and action-bound human approvals at the execution boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AutonomyMode(str, Enum):
    OBSERVE = "observe"
    SANDBOX_BUILD = "sandbox_build"
    DRAFT_DELIVERY = "draft_delivery"


class AutonomyAction(str, Enum):
    READ_REPOSITORY = "read_repository"
    READ_PROJECT_DOCUMENTATION = "read_project_documentation"
    INSPECT_TEST_RESULTS = "inspect_test_results"
    RUN_TESTS = "run_tests"
    SAVE_VALIDATED_LESSON = "save_validated_lesson"
    EXECUTE_REGISTERED_LOCAL_CAPABILITY = "execute_registered_local_capability"
    CREATE_EVIDENCE_REPORT = "create_evidence_report"
    WRITE_ISOLATED_SANDBOX = "write_isolated_sandbox"
    CREATE_FEATURE_BRANCH = "create_feature_branch"
    OPEN_DRAFT_PULL_REQUEST = "open_draft_pull_request"
    MERGE_PULL_REQUEST = "merge_pull_request"
    DEPLOY_PRODUCTION = "deploy_production"
    MODIFY_SECRETS = "modify_secrets"
    MODIFY_AUTHORIZATION = "modify_authorization"
    ENABLE_LIVE_PAYMENTS = "enable_live_payments"
    WRITE_PRODUCTION_DATA = "write_production_data"
    SEND_EXTERNAL_MESSAGE = "send_external_message"


@dataclass(frozen=True)
class AutonomyDecision:
    allowed: bool
    requires_human_approval: bool
    reason: str


_BASE_ACTIONS = frozenset({
    AutonomyAction.READ_REPOSITORY,
    AutonomyAction.READ_PROJECT_DOCUMENTATION,
    AutonomyAction.INSPECT_TEST_RESULTS,
    AutonomyAction.RUN_TESTS,
})

_SANDBOX_ACTIONS = _BASE_ACTIONS | frozenset({
    AutonomyAction.SAVE_VALIDATED_LESSON,
    AutonomyAction.WRITE_ISOLATED_SANDBOX,
    AutonomyAction.EXECUTE_REGISTERED_LOCAL_CAPABILITY,
    AutonomyAction.CREATE_EVIDENCE_REPORT,
})

_DRAFT_ACTIONS = _SANDBOX_ACTIONS | frozenset({
    AutonomyAction.CREATE_FEATURE_BRANCH,
    AutonomyAction.OPEN_DRAFT_PULL_REQUEST,
})

_ALWAYS_HUMAN_CONTROLLED = frozenset({
    AutonomyAction.MERGE_PULL_REQUEST,
    AutonomyAction.DEPLOY_PRODUCTION,
    AutonomyAction.MODIFY_SECRETS,
    AutonomyAction.MODIFY_AUTHORIZATION,
    AutonomyAction.ENABLE_LIVE_PAYMENTS,
    AutonomyAction.WRITE_PRODUCTION_DATA,
    AutonomyAction.SEND_EXTERNAL_MESSAGE,
})


@dataclass(frozen=True)
class ProfessorAutonomyPolicy:
    """A bounded autonomy mode; unknown modes/actions fail closed."""

    mode: AutonomyMode = AutonomyMode.OBSERVE

    def __post_init__(self) -> None:
        if not isinstance(self.mode, AutonomyMode):
            raise ValueError("A recognized Professor autonomy mode is required.")

    def decide(self, action: AutonomyAction) -> AutonomyDecision:
        if not isinstance(action, AutonomyAction):
            return AutonomyDecision(
                False, True, "Unknown actions are denied by default."
            )

        if action in _ALWAYS_HUMAN_CONTROLLED:
            return AutonomyDecision(
                False,
                True,
                "This action remains outside autonomous authority and requires a separate human-controlled workflow.",
            )

        if self.mode is AutonomyMode.OBSERVE:
            allowed_actions = _BASE_ACTIONS
        elif self.mode is AutonomyMode.SANDBOX_BUILD:
            allowed_actions = _SANDBOX_ACTIONS
        else:
            allowed_actions = _DRAFT_ACTIONS

        if action in allowed_actions:
            return AutonomyDecision(
                True,
                False,
                f"Action is permitted within the {self.mode.value} boundary.",
            )

        return AutonomyDecision(
            False,
            False,
            f"Action is not permitted within the {self.mode.value} boundary.",
        )

    def permits(self, action: AutonomyAction) -> bool:
        """Convenience predicate; callers should retain decide() for audit reasons."""
        return self.decide(action).allowed
