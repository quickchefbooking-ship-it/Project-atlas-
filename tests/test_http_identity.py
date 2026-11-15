import sqlite3
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from atlas_engine.http_identity import (
    IdentityVerifierUnavailable,
    VerifiedIdentityService,
    require_verified_principal,
)
from atlas_engine.oidc_contract import OIDCProviderConfig, VerifiedTokenClaims
from atlas_engine.tenant_membership import SQLiteMembershipRegistry


ISSUER = "https://identity.example.test/"
CONFIG = OIDCProviderConfig(
    issuer=ISSUER,
    audience="atlas-api",
    jwks_uri=ISSUER + ".well-known/jwks.json",
    allowed_algorithms=frozenset({"RS256"}),
)


class FakeVerifier:
    def __init__(self, claims=None, error=None):
        self.claims = claims
        self.error = error
        self.seen_token = None

    def verify(self, bearer_token):
        self.seen_token = bearer_token
        if self.error:
            raise self.error
        return self.claims


def _claims(**overrides):
    values = {
        "issuer": ISSUER,
        "subject": "user-a",
        "audiences": ("atlas-api",),
        "expires_at": int(time.time()) + 300,
        "not_before": int(time.time()) - 30,
        "roles": ("atlas_admin",),
    }
    values.update(overrides)
    return VerifiedTokenClaims(**values)


def _request(service=None):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(identity_service=service)))


def _registry(tmp_path):
    registry = SQLiteMembershipRegistry(str(tmp_path / "members.sqlite"))
    registry.initialize()
    registry.create_tenant("tenant-a", "Tenant A")
    registry.provision_membership(ISSUER, "user-a", "tenant-a", {"tasks:read"})
    return registry


def test_missing_identity_service_returns_503():
    with pytest.raises(HTTPException) as exc:
        require_verified_principal(_request(), "Bearer abc.def.ghi")
    assert exc.value.status_code == 503


@pytest.mark.parametrize("header", [None, "", "Basic abc", "Bearer", "Bearer a b", "Bearer abc\n"])
def test_missing_or_malformed_bearer_is_rejected(header):
    service = VerifiedIdentityService(CONFIG, FakeVerifier(_claims()), None)
    with pytest.raises(HTTPException) as exc:
        require_verified_principal(_request(service), header)
    assert exc.value.status_code == 401


def test_valid_bearer_resolves_only_server_side_membership(tmp_path):
    verifier = FakeVerifier(_claims())
    service = VerifiedIdentityService(CONFIG, verifier, _registry(tmp_path))
    principal = require_verified_principal(_request(service), "Bearer signed.token.value")
    assert principal.tenant_id == "tenant-a"
    assert principal.scopes == frozenset({"tasks:read"})
    assert verifier.seen_token == "signed.token.value"


def test_client_role_claim_does_not_grant_membership_scopes(tmp_path):
    registry = _registry(tmp_path)
    verifier = FakeVerifier(_claims(roles=("tenant_owner", "proposal_reviewer")))
    service = VerifiedIdentityService(CONFIG, verifier, registry)
    principal = require_verified_principal(_request(service), "Bearer signed.token.value")
    assert principal.scopes == frozenset({"tasks:read"})
    assert "lessons:review" not in principal.scopes


@pytest.mark.parametrize("claims", [
    _claims(expires_at=int(time.time()) - 120),
    _claims(not_before=int(time.time()) + 120),
    _claims(issuer="https://attacker.example/"),
    _claims(audiences=("another-api",)),
])
def test_invalid_registered_claims_are_rejected(tmp_path, claims):
    service = VerifiedIdentityService(CONFIG, FakeVerifier(claims), _registry(tmp_path))
    with pytest.raises(HTTPException) as exc:
        require_verified_principal(_request(service), "Bearer signed.token.value")
    assert exc.value.status_code == 401


def test_verifier_outage_returns_503_without_token_details(tmp_path):
    service = VerifiedIdentityService(
        CONFIG, FakeVerifier(error=IdentityVerifierUnavailable("private details")),
        _registry(tmp_path),
    )
    with pytest.raises(HTTPException) as exc:
        require_verified_principal(_request(service), "Bearer signed.token.value")
    assert exc.value.status_code == 503
    assert "private details" not in exc.value.detail


def test_ambiguous_membership_is_rejected_not_selected(tmp_path):
    registry = _registry(tmp_path)
    registry.create_tenant("tenant-b", "Tenant B")
    registry.provision_membership(ISSUER, "user-a", "tenant-b", {"tasks:write"})
    service = VerifiedIdentityService(CONFIG, FakeVerifier(_claims()), registry)
    with pytest.raises(HTTPException) as exc:
        require_verified_principal(_request(service), "Bearer signed.token.value")
    assert exc.value.status_code == 401



def test_membership_store_outage_returns_503(tmp_path):
    class BrokenMembershipStore:
        def resolve_membership(self, *_args, **_kwargs):
            raise sqlite3.OperationalError("private database details")

    service = VerifiedIdentityService(CONFIG, FakeVerifier(_claims()), BrokenMembershipStore())
    with pytest.raises(HTTPException) as exc:
        require_verified_principal(_request(service), "Bearer signed.token.value")
    assert exc.value.status_code == 503
    assert "private database details" not in exc.value.detail


class FakeAtlasSessions:
    def __init__(self, valid=True):
        self.valid = valid
        self.seen_session = None
        self.seen_csrf = None

    def validate_csrf_token(self, session_token, csrf_token):
        self.seen_session = session_token
        self.seen_csrf = csrf_token
        return self.valid


class FakeAtlasSessionIdentity:
    def __init__(self, valid_csrf=True):
        self.sessions = FakeAtlasSessions(valid_csrf)
        self.seen_session = None

    def authenticate(self, session_token):
        self.seen_session = session_token
        return "atlas-principal"


def _cookie_request(method="GET", *, origin=None, fetch_site="same-origin",
                    csrf="csrf-token", valid_csrf=True):
    service = FakeAtlasSessionIdentity(valid_csrf)
    headers = {"sec-fetch-site": fetch_site}
    if origin is not None:
        headers["origin"] = origin
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(
            identity_service=None,
            atlas_session_identity_service=service,
            atlas_trusted_origins=frozenset({"https://atlas.example.test"}),
        )),
        cookies={"__Host-atlas_session": "opaque-session-token"},
        headers=headers,
        method=method,
    )
    return request, service, csrf


def test_atlas_cookie_authenticates_safe_request_without_csrf_header():
    request, service, _ = _cookie_request()
    principal = require_verified_principal(request)
    assert principal == "atlas-principal"
    assert service.seen_session == "opaque-session-token"


def test_atlas_cookie_rejects_state_change_without_trusted_origin():
    request, _, csrf = _cookie_request("POST", csrf="valid-csrf")
    with pytest.raises(HTTPException) as exc:
        require_verified_principal(request, csrf_token=csrf)
    assert exc.value.status_code == 403


def test_atlas_cookie_rejects_untrusted_origin_even_with_valid_csrf():
    request, _, csrf = _cookie_request(
        "POST", origin="https://attacker.example", csrf="valid-csrf"
    )
    with pytest.raises(HTTPException) as exc:
        require_verified_principal(request, csrf_token=csrf)
    assert exc.value.status_code == 403


def test_atlas_cookie_requires_session_bound_csrf_for_state_change():
    request, service, csrf = _cookie_request(
        "POST", origin="https://atlas.example.test", valid_csrf=False
    )
    with pytest.raises(HTTPException) as exc:
        require_verified_principal(request, csrf_token=csrf)
    assert exc.value.status_code == 403
    assert service.sessions.seen_session == "opaque-session-token"


def test_atlas_cookie_accepts_trusted_origin_and_valid_csrf():
    request, service, csrf = _cookie_request(
        "POST", origin="https://atlas.example.test", valid_csrf=True
    )
    principal = require_verified_principal(request, csrf_token=csrf)
    assert principal == "atlas-principal"
    assert service.sessions.seen_csrf == csrf


def test_atlas_cookie_rejects_cross_site_fetch_metadata():
    request, _, csrf = _cookie_request(
        "POST", origin="https://atlas.example.test", fetch_site="cross-site"
    )
    with pytest.raises(HTTPException) as exc:
        require_verified_principal(request, csrf_token=csrf)
    assert exc.value.status_code == 403
