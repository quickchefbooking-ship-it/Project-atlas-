import time

from fastapi.testclient import TestClient

import app as app_module
from atlas_engine.capability_registry import CapabilityDefinition, CapabilityRegistry
from atlas_engine.http_identity import VerifiedIdentityService
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.oidc_contract import OIDCProviderConfig, VerifiedTokenClaims
from atlas_engine.tenant_membership import SQLiteMembershipRegistry


ISSUER = "https://identity.prepare.example.test/"
CONFIG = OIDCProviderConfig(
    issuer=ISSUER,
    audience="atlas-api",
    jwks_uri=ISSUER + ".well-known/jwks.json",
    allowed_algorithms=frozenset({"RS256"}),
)
SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


class SubjectVerifier:
    def __init__(self):
        self.subject = "alice"

    def verify(self, _token):
        now = int(time.time())
        return VerifiedTokenClaims(
            issuer=ISSUER,
            subject=self.subject,
            audiences=("atlas-api",),
            expires_at=now + 300,
            not_before=now - 10,
            roles=(),
        )


def setup_client(monkeypatch, tmp_path, registry):
    from atlas_engine import storage

    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "core.sqlite"))
    storage.init_db()
    monkeypatch.setenv("ATLAS_TENANT_DATA_DB_PATH", str(tmp_path / "tenant.sqlite"))
    monkeypatch.setenv("ATLAS_MEMBERSHIP_DB_PATH", str(tmp_path / "memberships.sqlite"))
    for name in (
        "ATLAS_OIDC_ISSUER", "ATLAS_OIDC_AUDIENCE",
        "ATLAS_OIDC_JWKS_URI", "ATLAS_OIDC_ALLOWED_ALGORITHMS",
    ):
        monkeypatch.delenv(name, raising=False)

    memberships = SQLiteMembershipRegistry(str(tmp_path / "memberships.sqlite"))
    memberships.initialize()
    memberships.create_tenant("tenant-a", "Tenant A")
    memberships.provision_membership(
        ISSUER, "alice", "tenant-a",
        {"plans:read", "plans:write", "steps:read", "knowledge:read"},
    )
    client = TestClient(app_module.app)
    client.__enter__()
    verifier = SubjectVerifier()
    app_module.app.state.identity_service = VerifiedIdentityService(
        CONFIG, verifier, memberships
    )
    app_module.app.state.tenant_capability_registry = registry
    return client


def create_plan(client, capability="knowledge.search"):
    response = client.post(
        "/professor/tenant/plans",
        headers={"Authorization": "Bearer valid-test-token"},
        json={
            "objective": "Research a question",
            "acceptance_criteria": ["Evidence is recorded"],
            "steps": [{
                "step_id": "search",
                "capability": capability,
                "objective": "Find evidence",
                "risk": "read_only",
                "required_scopes": ["knowledge:read"],
                "capability_version": "1",
            }],
        },
    )
    assert response.status_code == 201
    return response.json()["plan_id"]


def test_prepare_moves_draft_to_ready_only_after_complete_policy_preview(monkeypatch, tmp_path):
    registry = CapabilityRegistry((CapabilityDefinition(
        "knowledge.search", "1", "read_only", SCHEMA, SCHEMA,
        required_scopes=("knowledge:read",),
    ),))
    client = setup_client(monkeypatch, tmp_path, registry)
    try:
        plan_id = create_plan(client)
        response = client.post(
            f"/professor/tenant/plans/{plan_id}/prepare",
            headers={"Authorization": "Bearer valid-test-token"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "prepared"
        assert body["state"] == "ready"
        assert body["readiness"]["structurally_ready_step_ids"] == ["search"]
        assert body["readiness"]["blocked_step_ids"] == []
        assert body["execution_enabled"] is False

        inspected = client.get(
            f"/professor/tenant/plans/{plan_id}",
            headers={"Authorization": "Bearer valid-test-token"},
        )
        assert inspected.status_code == 200
        assert inspected.json()["plan"]["state"] == "ready"
        assert inspected.json()["readiness"]["steps"][0]["readiness"] == "structurally_ready"

        second_prepare = client.post(
            f"/professor/tenant/plans/{plan_id}/prepare",
            headers={"Authorization": "Bearer valid-test-token"},
        )
        assert second_prepare.status_code == 409
    finally:
        client.__exit__(None, None, None)


def test_prepare_leaves_draft_unchanged_when_capability_is_unknown(monkeypatch, tmp_path):
    client = setup_client(monkeypatch, tmp_path, CapabilityRegistry())
    try:
        plan_id = create_plan(client)
        response = client.post(
            f"/professor/tenant/plans/{plan_id}/prepare",
            headers={"Authorization": "Bearer valid-test-token"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "blocked"
        assert body["state"] == "draft"
        assert body["readiness"]["blocked_step_ids"] == ["search"]
        assert body["readiness"]["steps"][0]["readiness"] == "blocked_missing_capability"
        assert body["execution_enabled"] is False

        inspected = client.get(
            f"/professor/tenant/plans/{plan_id}",
            headers={"Authorization": "Bearer valid-test-token"},
        )
        assert inspected.status_code == 200
        assert inspected.json()["plan"]["state"] == "draft"
        assert len(inspected.json()["transitions"]) == 1
    finally:
        client.__exit__(None, None, None)


def test_prepare_requires_verified_identity_and_never_accepts_api_key(monkeypatch, tmp_path):
    client = setup_client(monkeypatch, tmp_path, CapabilityRegistry())
    try:
        plan_id = create_plan(client)
        response = client.post(
            f"/professor/tenant/plans/{plan_id}/prepare",
            headers={"X-API-Key": "not-a-human-session"},
        )
        assert response.status_code == 401
    finally:
        client.__exit__(None, None, None)
