import pytest

from atlas_engine.professor_autonomy_policy import (
    AutonomyAction,
    AutonomyMode,
    ProfessorAutonomyPolicy,
)


@pytest.mark.parametrize("action", [
    AutonomyAction.READ_REPOSITORY,
    AutonomyAction.READ_PROJECT_DOCUMENTATION,
    AutonomyAction.INSPECT_TEST_RESULTS,
    AutonomyAction.RUN_TESTS,
])
def test_observe_mode_allows_read_only_engineering_actions(action):
    assert ProfessorAutonomyPolicy(AutonomyMode.OBSERVE).permits(action)


def test_observe_mode_cannot_write_or_create_delivery_artifacts():
    policy = ProfessorAutonomyPolicy(AutonomyMode.OBSERVE)
    assert not policy.permits(AutonomyAction.WRITE_ISOLATED_SANDBOX)
    assert not policy.permits(AutonomyAction.CREATE_FEATURE_BRANCH)
    assert not policy.permits(AutonomyAction.OPEN_DRAFT_PULL_REQUEST)


def test_sandbox_mode_can_build_in_isolation_and_save_validated_learning():
    policy = ProfessorAutonomyPolicy(AutonomyMode.SANDBOX_BUILD)
    assert policy.permits(AutonomyAction.WRITE_ISOLATED_SANDBOX)
    assert policy.permits(AutonomyAction.SAVE_VALIDATED_LESSON)
    assert not policy.permits(AutonomyAction.CREATE_FEATURE_BRANCH)
    assert not policy.permits(AutonomyAction.OPEN_DRAFT_PULL_REQUEST)


def test_draft_delivery_mode_can_create_reviewable_git_artifacts():
    policy = ProfessorAutonomyPolicy(AutonomyMode.DRAFT_DELIVERY)
    assert policy.permits(AutonomyAction.WRITE_ISOLATED_SANDBOX)
    assert policy.permits(AutonomyAction.CREATE_FEATURE_BRANCH)
    assert policy.permits(AutonomyAction.OPEN_DRAFT_PULL_REQUEST)


@pytest.mark.parametrize("action", [
    AutonomyAction.MERGE_PULL_REQUEST,
    AutonomyAction.DEPLOY_PRODUCTION,
    AutonomyAction.MODIFY_SECRETS,
    AutonomyAction.MODIFY_AUTHORIZATION,
    AutonomyAction.ENABLE_LIVE_PAYMENTS,
    AutonomyAction.WRITE_PRODUCTION_DATA,
    AutonomyAction.SEND_EXTERNAL_MESSAGE,
])
@pytest.mark.parametrize("mode", list(AutonomyMode))
def test_high_impact_actions_are_never_granted_by_autonomy_mode(action, mode):
    decision = ProfessorAutonomyPolicy(mode).decide(action)
    assert not decision.allowed
    assert decision.requires_human_approval


def test_unknown_action_fails_closed():
    decision = ProfessorAutonomyPolicy(AutonomyMode.DRAFT_DELIVERY).decide("shell.exec")
    assert not decision.allowed
    assert decision.requires_human_approval


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="recognized"):
        ProfessorAutonomyPolicy("unrestricted")


def test_decision_explains_the_boundary():
    decision = ProfessorAutonomyPolicy(AutonomyMode.DRAFT_DELIVERY).decide(
        AutonomyAction.OPEN_DRAFT_PULL_REQUEST
    )
    assert decision.allowed
    assert "draft_delivery" in decision.reason
