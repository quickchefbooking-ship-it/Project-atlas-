"""Narrow tenant membership administration façade.

Call only from trusted server-side provisioning code after the configured
identity adapter has created the RequestPrincipal. This module is not an HTTP
authentication mechanism; never construct principals from request payloads.
"""
from .identity_policy import AuthorizationDenied, RequestPrincipal, authorize_tenant_resource
from .tenant_membership import SQLiteMembershipRegistry

MEMBERSHIP_ADMIN_SCOPE = "tenant:members:manage"


def _authorise_membership_admin(principal: RequestPrincipal) -> None:
    if not isinstance(principal, RequestPrincipal):
        raise AuthorizationDenied("Verified request principal required.")
    authorize_tenant_resource(
        principal, principal.tenant_id, {MEMBERSHIP_ADMIN_SCOPE}
    )


def provision_tenant_member(registry, principal, issuer, subject, scopes) -> None:
    """Provision/reactivate a member only within the administrator's tenant."""
    if not isinstance(registry, SQLiteMembershipRegistry):
        raise TypeError("A server-controlled membership registry is required.")
    _authorise_membership_admin(principal)
    registry.provision_membership(
        issuer, subject, principal.tenant_id, scopes, _actor=principal
    )


def revoke_tenant_member(registry, principal, issuer, subject) -> bool:
    """Revoke a member only within the administrator's tenant."""
    if not isinstance(registry, SQLiteMembershipRegistry):
        raise TypeError("A server-controlled membership registry is required.")
    _authorise_membership_admin(principal)
    return registry.revoke_membership(
        issuer, subject, principal.tenant_id, _actor=principal
    )
