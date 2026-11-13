"""Fail-closed authorization primitives for a future verified request principal.

This module deliberately does not authenticate tokens or create principals from
HTTP input. A trusted OIDC integration must construct RequestPrincipal only
after signature, issuer, audience, time and membership checks have succeeded.
"""
from dataclasses import dataclass
from typing import FrozenSet, Iterable


class AuthorizationDenied(PermissionError):
    """Raised when a principal cannot access a tenant-scoped resource."""


@dataclass(frozen=True)
class RequestPrincipal:
    """Immutable identity context created by trusted server-side auth code."""

    issuer: str
    subject: str
    tenant_id: str
    membership_active: bool
    scopes: FrozenSet[str]

    def __post_init__(self) -> None:
        for field_name in ("issuer", "subject", "tenant_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string.")
            if len(value) > 512:
                raise ValueError(f"{field_name} exceeds the permitted length.")
        if not isinstance(self.membership_active, bool):
            raise ValueError("membership_active must be a boolean.")
        if not isinstance(self.scopes, frozenset):
            raise ValueError("scopes must be an immutable frozenset.")
        if any(
            not isinstance(scope, str) or not scope.strip() or len(scope) > 128
            for scope in self.scopes
        ):
            raise ValueError("Each scope must be a non-empty string of at most 128 characters.")


def authorize_tenant_resource(
    principal: RequestPrincipal,
    resource_tenant_id: str,
    required_scopes: Iterable[str] = (),
) -> None:
    """Fail closed unless active membership, tenant and every required scope match.

    The caller must obtain both the principal and resource tenant from trusted
    server-side sources. Never pass tenant IDs or scopes directly from a client
    request as proof of authorisation.
    """
    if not isinstance(principal, RequestPrincipal):
        raise AuthorizationDenied("Verified request principal required.")
    if not principal.membership_active:
        raise AuthorizationDenied("Active tenant membership required.")
    if not isinstance(resource_tenant_id, str) or not resource_tenant_id.strip():
        raise AuthorizationDenied("Tenant-scoped resource required.")
    if principal.tenant_id != resource_tenant_id:
        # Keep the denial generic to avoid confirming another tenant's records.
        raise AuthorizationDenied("Resource access denied.")

    try:
        required = frozenset(required_scopes)
    except (TypeError, ValueError):
        raise AuthorizationDenied("Valid capability scopes required.") from None
    if any(
        not isinstance(scope, str) or not scope.strip() or len(scope) > 128
        for scope in required
    ):
        raise AuthorizationDenied("Valid capability scopes required.")
    if not required.issubset(principal.scopes):
        raise AuthorizationDenied("Required capability scope is missing.")
