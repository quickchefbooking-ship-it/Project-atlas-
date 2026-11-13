import pytest

from atlas_engine.identity_policy import (
    AuthorizationDenied,
    RequestPrincipal,
    authorize_tenant_resource,
)


def _principal(**overrides):
    values = {
        "issuer": "https://identity.example.test/",
        "subject": "user-123",
        "tenant_id": "tenant-a",
        "membership_active": True,
        "scopes": frozenset({"tasks:read", "sources:read"}),
    }
    values.update(overrides)
    return RequestPrincipal(**values)


def test_active_principal_can_access_own_tenant_with_required_scope():
    authorize_tenant_resource(_principal(), "tenant-a", {"tasks:read"})


def test_cross_tenant_access_is_denied_without_disclosing_target():
    with pytest.raises(AuthorizationDenied, match="Resource access denied"):
        authorize_tenant_resource(_principal(), "tenant-b", {"tasks:read"})


def test_revoked_membership_is_denied_even_when_scope_is_present():
    with pytest.raises(AuthorizationDenied, match="Active tenant membership"):
        authorize_tenant_resource(
            _principal(membership_active=False), "tenant-a", {"tasks:read"}
        )


def test_missing_scope_is_denied():
    with pytest.raises(AuthorizationDenied, match="scope is missing"):
        authorize_tenant_resource(_principal(), "tenant-a", {"tasks:write"})


def test_all_required_scopes_must_be_present():
    with pytest.raises(AuthorizationDenied):
        authorize_tenant_resource(
            _principal(), "tenant-a", {"tasks:read", "tasks:write"}
        )


@pytest.mark.parametrize("tenant_id", ["", " ", None, 42])
def test_invalid_resource_tenant_is_denied(tenant_id):
    with pytest.raises(AuthorizationDenied):
        authorize_tenant_resource(_principal(), tenant_id)


def test_unverified_or_arbitrary_object_is_not_accepted_as_principal():
    with pytest.raises(AuthorizationDenied, match="Verified request principal"):
        authorize_tenant_resource(
            {"tenant_id": "tenant-a", "scopes": ["tasks:read"]}, "tenant-a"
        )


@pytest.mark.parametrize("field,value", [
    ("issuer", ""),
    ("subject", " "),
    ("tenant_id", ""),
    ("membership_active", "true"),
    ("scopes", {"tasks:read"}),
])
def test_principal_rejects_invalid_or_mutable_fields(field, value):
    values = {
        "issuer": "https://identity.example.test/",
        "subject": "user-123",
        "tenant_id": "tenant-a",
        "membership_active": True,
        "scopes": frozenset({"tasks:read"}),
    }
    values[field] = value
    with pytest.raises(ValueError):
        RequestPrincipal(**values)


def test_principal_is_immutable():
    principal = _principal()
    with pytest.raises((AttributeError, TypeError)):
        principal.tenant_id = "tenant-b"


def test_invalid_scope_request_fails_closed():
    with pytest.raises(AuthorizationDenied, match="Valid capability scopes"):
        authorize_tenant_resource(_principal(), "tenant-a", [None])
