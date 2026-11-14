import pytest

from atlas_engine.scope_policy import (
    ALLOWED_SCOPES,
    PROVIDER_ROLE_SCOPE_MAP,
    ScopeMappingError,
    scopes_for_verified_roles,
)


def test_viewer_role_maps_only_to_read_scopes():
    scopes = scopes_for_verified_roles({"atlas_viewer"})
    assert scopes
    assert all(scope.endswith(":read") for scope in scopes)


def test_operator_role_maps_to_bounded_application_scopes():
    scopes = scopes_for_verified_roles({"atlas_operator"})
    assert scopes == PROVIDER_ROLE_SCOPE_MAP["atlas_operator"]
    assert scopes <= ALLOWED_SCOPES
    assert "proposals:review" not in scopes


def test_unknown_provider_roles_grant_nothing():
    assert scopes_for_verified_roles({"org_owner", "billing_admin"}) == frozenset()


def test_mixed_known_and_unknown_roles_only_grant_known_scopes():
    assert scopes_for_verified_roles({"atlas_viewer", "super_admin"}) == scopes_for_verified_roles({"atlas_viewer"})


@pytest.mark.parametrize("roles", ["atlas_operator", b"atlas_operator", [None], [""], [42]])
def test_malformed_role_claims_fail_closed(roles):
    with pytest.raises(ScopeMappingError):
        scopes_for_verified_roles(roles)


def test_empty_roles_grant_no_scopes():
    assert scopes_for_verified_roles([]) == frozenset()


def test_policy_does_not_accept_client_requested_scopes():
    # The only input is a verified-role collection; there is no scopes parameter.
    assert scopes_for_verified_roles({"atlas_viewer"}) == frozenset({
        "tasks:read", "evaluations:read", "lessons:read", "proposals:read",
    })


def test_tenant_membership_admin_scope_is_not_granted_to_starter_roles():
    assert "tenant:members:manage" in ALLOWED_SCOPES
    assert all(
        "tenant:members:manage" not in scopes
        for scopes in PROVIDER_ROLE_SCOPE_MAP.values()
    )
