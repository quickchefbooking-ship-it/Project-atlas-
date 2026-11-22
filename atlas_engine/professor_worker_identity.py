"""Server-side identity boundary for the dedicated Professor worker.

This module does not authenticate HTTP callers or start a worker. Trusted
application composition must supply an explicit, tenant-scoped grant. The
resulting RequestPrincipal is minted only inside the worker process and uses
a reserved internal issuer so it cannot be confused with a human OIDC subject.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .identity_policy import RequestPrincipal


WORKER_ISSUER = "urn:atlasonepro:internal-professor-worker"

WORKER_CONTROL_SCOPES = frozenset({
    "plans:read",
    "plans:execute",
    "steps:claim",
    "steps:heartbeat",
    "steps:complete",
    "steps:read",
})

# First worker slice only: deterministic local computation. Additional
# capability scopes must be added deliberately after reviewing the handler.
WORKER_CAPABILITY_SCOPES = frozenset({"compute:local"})
WORKER_ALLOWED_SCOPES = WORKER_CONTROL_SCOPES | WORKER_CAPABILITY_SCOPES
_WORKER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class WorkerIdentityUnavailable(RuntimeError):
    """The dedicated worker identity is disabled or lacks a tenant grant."""


@dataclass(frozen=True)
class WorkerTenantGrant:
    """One deployment-owned tenant assignment with a narrow immutable scope set."""

    tenant_id: str
    scopes: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, str) or not self.tenant_id.strip() or len(self.tenant_id) > 512:
            raise ValueError("A bounded tenant identifier is required.")
        if not isinstance(self.scopes, frozenset):
            raise ValueError("Worker scopes must be an immutable frozenset.")
        if any(not isinstance(scope, str) or not scope.strip() or len(scope) > 128 for scope in self.scopes):
            raise ValueError("Worker scopes must be non-empty bounded strings.")
        unknown = self.scopes - WORKER_ALLOWED_SCOPES
        if unknown:
            raise ValueError("Worker grant contains a scope outside the approved first-slice allowlist.")
        if not WORKER_CONTROL_SCOPES.issubset(self.scopes):
            raise ValueError("Worker grant is missing required orchestration scopes.")


@dataclass(frozen=True)
class ProfessorWorkerIdentityConfig:
    """Trusted process configuration; never construct this from HTTP request data."""

    worker_id: str
    enabled: bool = False
    tenant_grants: tuple[WorkerTenantGrant, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.worker_id, str) or not _WORKER_ID.fullmatch(self.worker_id):
            raise ValueError("Worker ID must be a bounded server-assigned identifier.")
        if type(self.enabled) is not bool:
            raise ValueError("Worker enabled flag must be a boolean.")
        if not isinstance(self.tenant_grants, tuple) or any(
            not isinstance(grant, WorkerTenantGrant) for grant in self.tenant_grants
        ):
            raise ValueError("Worker tenant grants must be an immutable tuple.")
        tenant_ids = [grant.tenant_id for grant in self.tenant_grants]
        if len(tenant_ids) != len(set(tenant_ids)):
            raise ValueError("Worker tenant grants must not contain duplicate tenants.")
        if self.enabled and not self.tenant_grants:
            raise ValueError("An enabled worker must have at least one explicit tenant grant.")


@dataclass(frozen=True)
class ProfessorWorkerIdentityService:
    """Mint internal principals only for explicitly assigned tenants."""

    config: ProfessorWorkerIdentityConfig

    def __post_init__(self) -> None:
        if not isinstance(self.config, ProfessorWorkerIdentityConfig):
            raise TypeError("Trusted ProfessorWorkerIdentityConfig is required.")

    def principal_for_tenant(self, tenant_id: str) -> RequestPrincipal:
        if not self.config.enabled:
            raise WorkerIdentityUnavailable("Professor worker identity is disabled.")
        if not isinstance(tenant_id, str) or not tenant_id.strip() or len(tenant_id) > 512:
            raise WorkerIdentityUnavailable("Professor worker tenant assignment is unavailable.")
        grant = next(
            (item for item in self.config.tenant_grants if item.tenant_id == tenant_id),
            None,
        )
        if grant is None:
            raise WorkerIdentityUnavailable("Professor worker tenant assignment is unavailable.")
        return RequestPrincipal(
            issuer=WORKER_ISSUER,
            subject=self.config.worker_id,
            tenant_id=grant.tenant_id,
            membership_active=True,
            scopes=grant.scopes,
        )
