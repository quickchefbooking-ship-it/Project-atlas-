import pytest
from dataclasses import FrozenInstanceError

from atlas_engine.identity_policy import AuthorizationDenied, RequestPrincipal, authorize_tenant_resource
from atlas_engine.professor_worker_identity import (
    ProfessorWorkerIdentityConfig,
    ProfessorWorkerIdentityService,
    WORKER_ALLOWED_SCOPES,
    WORKER_CONTROL_SCOPES,
    WORKER_ISSUER,
    WorkerIdentityUnavailable,
    WorkerTenantGrant,
)


def grant(tenant_id="tenant-a", extra_scopes=frozenset()):
    return WorkerTenantGrant(
        tenant_id=tenant_id,
        scopes=WORKER_CONTROL_SCOPES | frozenset(extra_scopes),
    )


def test_worker_identity_is_disabled_by_default():
    service = ProfessorWorkerIdentityService(
        ProfessorWorkerIdentityConfig(worker_id="professor-worker-01")
    )
    with pytest.raises(WorkerIdentityUnavailable, match="disabled"):
        service.principal_for_tenant("tenant-a")


def test_enabled_worker_gets_distinct_server_minted_tenant_principal():
    service = ProfessorWorkerIdentityService(
        ProfessorWorkerIdentityConfig(
            worker_id="professor-worker-01",
            enabled=True,
            tenant_grants=(grant(extra_scopes={"compute:local"}),),
        )
    )
    principal = service.principal_for_tenant("tenant-a")
    assert isinstance(principal, RequestPrincipal)
    assert principal.issuer == WORKER_ISSUER
    assert principal.subject == "professor-worker-01"
    assert principal.tenant_id == "tenant-a"
    assert principal.membership_active is True
    assert principal.scopes == WORKER_CONTROL_SCOPES | {"compute:local"}


def test_worker_identity_does_not_impersonate_a_human_subject():
    service = ProfessorWorkerIdentityService(
        ProfessorWorkerIdentityConfig(
            worker_id="professor-worker-01",
            enabled=True,
            tenant_grants=(grant(),),
        )
    )
    worker = service.principal_for_tenant("tenant-a")
    human = RequestPrincipal(
        issuer="https://identity.example",
        subject="user-123",
        tenant_id="tenant-a",
        membership_active=True,
        scopes=WORKER_CONTROL_SCOPES,
    )
    assert worker.issuer != human.issuer
    assert worker.subject != human.subject


def test_worker_identity_is_tenant_scoped_and_has_no_wildcard_grant():
    service = ProfessorWorkerIdentityService(
        ProfessorWorkerIdentityConfig(
            worker_id="professor-worker-01",
            enabled=True,
            tenant_grants=(grant("tenant-a"),),
        )
    )
    with pytest.raises(WorkerIdentityUnavailable):
        service.principal_for_tenant("tenant-b")
    with pytest.raises(WorkerIdentityUnavailable):
        service.principal_for_tenant("*")


def test_worker_principal_passes_only_its_explicit_tenant_and_scopes():
    service = ProfessorWorkerIdentityService(
        ProfessorWorkerIdentityConfig(
            worker_id="professor-worker-01",
            enabled=True,
            tenant_grants=(grant("tenant-a"),),
        )
    )
    principal = service.principal_for_tenant("tenant-a")
    authorize_tenant_resource(principal, "tenant-a", {"steps:claim"})
    with pytest.raises(AuthorizationDenied):
        authorize_tenant_resource(principal, "tenant-b", {"steps:claim"})
    with pytest.raises(AuthorizationDenied):
        authorize_tenant_resource(principal, "tenant-a", {"payments:write"})


def test_worker_scope_allowlist_rejects_unreviewed_capability_and_privileged_scopes():
    with pytest.raises(ValueError, match="allowlist"):
        WorkerTenantGrant(
            "tenant-a",
            WORKER_CONTROL_SCOPES | {"payments:write"},
        )
    with pytest.raises(ValueError, match="allowlist"):
        WorkerTenantGrant(
            "tenant-a",
            WORKER_CONTROL_SCOPES | {"shell:execute"},
        )
    assert WORKER_ALLOWED_SCOPES == WORKER_CONTROL_SCOPES | {"compute:local"}


def test_worker_grant_must_include_all_orchestration_scopes():
    with pytest.raises(ValueError, match="required orchestration"):
        WorkerTenantGrant("tenant-a", frozenset({"plans:read"}))


def test_worker_configuration_rejects_duplicate_tenant_grants():
    with pytest.raises(ValueError, match="duplicate"):
        ProfessorWorkerIdentityConfig(
            worker_id="professor-worker-01",
            enabled=True,
            tenant_grants=(grant(), grant()),
        )


def test_enabled_worker_requires_explicit_tenant_grant():
    with pytest.raises(ValueError, match="explicit tenant grant"):
        ProfessorWorkerIdentityConfig(
            worker_id="professor-worker-01",
            enabled=True,
        )


def test_worker_configuration_is_immutable_and_validates_server_identity():
    config = ProfessorWorkerIdentityConfig(
        worker_id="professor-worker-01",
        enabled=True,
        tenant_grants=(grant(),),
    )
    with pytest.raises(FrozenInstanceError):
        config.enabled = False
    with pytest.raises(ValueError, match="server-assigned"):
        ProfessorWorkerIdentityConfig(worker_id="owner admin", enabled=True, tenant_grants=(grant(),))


def test_worker_grant_is_immutable():
    item = grant()
    with pytest.raises(FrozenInstanceError):
        item.tenant_id = "tenant-b"
