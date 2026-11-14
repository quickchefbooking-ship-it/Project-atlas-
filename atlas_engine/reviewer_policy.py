"""Fail-closed policy for proposal review by a verified human principal.

This is a policy primitive only. It is intentionally not wired to the HTTP
review route until a trusted identity provider and server-side principal
construction are configured.
"""

from .identity_policy import AuthorizationDenied, RequestPrincipal


REVIEW_SCOPE = "lessons:review"


def authorize_proposal_review(principal: RequestPrincipal) -> None:
    """Require a trusted, active tenant member with the proposal-review scope.

    The principal must be constructed by trusted server-side authentication
    code. Request payload fields such as ``approved_by`` are audit labels only
    and must never be passed here as identity proof.
    """
    if not isinstance(principal, RequestPrincipal):
        raise AuthorizationDenied("Verified reviewer principal required.")
    if not principal.membership_active:
        raise AuthorizationDenied("Active reviewer membership required.")
    if REVIEW_SCOPE not in principal.scopes:
        raise AuthorizationDenied("Proposal review scope is required.")
