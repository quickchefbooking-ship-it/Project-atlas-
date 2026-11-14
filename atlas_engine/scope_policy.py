"""Allowlisted mapping from verified provider roles to narrow app scopes.

This is policy, not token verification. Call only with roles extracted from a
cryptographically verified token by the future server-side OIDC adapter.
Unknown provider roles grant no permissions; client-requested scopes are never
accepted by this module.
"""
from types import MappingProxyType
from typing import Iterable, FrozenSet


ALLOWED_SCOPES = frozenset({
    "tasks:read", "tasks:write",
    "evaluations:read", "evaluations:write",
    "lessons:read", "lessons:write",
    "proposals:read", "proposals:write",
})

# Deliberately narrow starter policy. Proposal review is not granted here.
PROVIDER_ROLE_SCOPE_MAP = MappingProxyType({
    "atlas_viewer": frozenset({
        "tasks:read", "evaluations:read", "lessons:read", "proposals:read",
    }),
    "atlas_operator": frozenset({
        "tasks:read", "tasks:write",
        "evaluations:read", "evaluations:write",
        "lessons:read", "lessons:write",
        "proposals:read", "proposals:write",
    }),
})


class ScopeMappingError(ValueError):
    """Verified provider role data is malformed or violates local policy."""


def scopes_for_verified_roles(roles: Iterable[str]) -> FrozenSet[str]:
    """Return only locally allowlisted scopes for verified provider roles.

    Unknown roles are ignored and grant nothing. A bare string is rejected to
    avoid accidentally treating a role name as an iterable of characters.
    """
    if isinstance(roles, (str, bytes)):
        raise ScopeMappingError("Provider roles must be an iterable of role strings.")
    try:
        role_set = frozenset(roles)
    except (TypeError, ValueError):
        raise ScopeMappingError("Provider roles are malformed.") from None
    if any(not isinstance(role, str) or not role.strip() or len(role) > 128
           for role in role_set):
        raise ScopeMappingError("Each provider role must be a non-empty string.")
    scopes = frozenset(
        scope
        for role in role_set
        for scope in PROVIDER_ROLE_SCOPE_MAP.get(role, frozenset())
    )
    if not scopes.issubset(ALLOWED_SCOPES):
        raise ScopeMappingError("Local role policy contains an unapproved scope.")
    return scopes
