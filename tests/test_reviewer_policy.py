import pytest

from atlas_engine.identity_policy import AuthorizationDenied, RequestPrincipal
from atlas_engine.reviewer_policy import REVIEW_SCOPE, authorize_proposal_review


def principal(**overrides):
    values = {
        "issuer": "https://identity.example.test/",
        "subject": "reviewer-123",
        "tenant_id": "tenant-a",
        "membership_active": True,
        "scopes": frozenset({REVIEW_SCOPE}),
    }
    values.update(overrides)
    return RequestPrincipal(**values)


def test_active_verified_reviewer_with_scope_is_authorized():
    assert authorize_proposal_review(principal()) is None


def test_unverified_payload_like_object_is_denied():
    with pytest.raises(AuthorizationDenied, match="Verified reviewer principal"):
        authorize_proposal_review({"approved_by": "Ashley", "scopes": [REVIEW_SCOPE]})


def test_inactive_reviewer_is_denied():
    with pytest.raises(AuthorizationDenied, match="Active reviewer membership"):
        authorize_proposal_review(principal(membership_active=False))


def test_missing_review_scope_is_denied():
    with pytest.raises(AuthorizationDenied, match="Proposal review scope"):
        authorize_proposal_review(principal(scopes=frozenset({"tasks:read"})))


def test_arbitrary_reviewer_label_cannot_grant_authority():
    # Labels belong in audit metadata; only the server-created principal grants authority.
    with pytest.raises(AuthorizationDenied):
        authorize_proposal_review({"approved_by": "admin", "tenant_id": "tenant-a"})
