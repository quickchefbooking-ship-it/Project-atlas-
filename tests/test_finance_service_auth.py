from dataclasses import fields
from datetime import datetime, timezone

import pytest

from atlas_engine.finance_service_auth import (
    FINANCE_PORTFOLIO_READ,
    AuthorizedFinanceService,
    FinanceServiceTrustPolicy,
    ServiceAuthorizationError,
    VerifiedServiceTokenClaims,
    authorize_finance_service,
)


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
STAMP = int(NOW.timestamp())


def policy(**overrides):
    values = {
        "trusted_issuer": "https://identity.example.test",
        "expected_audience": "atlas-finance-bridge",
        "allowed_subjects": frozenset({"trading-bridge-demo"}),
        "maximum_lifetime_seconds": 300,
        "clock_skew_seconds": 0,
    }
    values.update(overrides)
    return FinanceServiceTrustPolicy(**values)


def claims(**overrides):
    values = {
        "issuer": "https://identity.example.test",
        "subject": "trading-bridge-demo",
        "audience": "atlas-finance-bridge",
        "issued_at": STAMP - 30,
        "not_before": STAMP - 30,
        "expires_at": STAMP + 120,
        "token_id": "jti-demo-001",
        "scopes": (FINANCE_PORTFOLIO_READ,),
        "environment": "demo",
    }
    values.update(overrides)
    return VerifiedServiceTokenClaims(**values)


def test_authorizes_allowlisted_demo_read_principal():
    result = authorize_finance_service(claims(), policy(), now=NOW)
    assert isinstance(result, AuthorizedFinanceService)
    assert result.subject == "trading-bridge-demo"
    assert result.scopes == frozenset({FINANCE_PORTFOLIO_READ})
    assert result.environment == "demo"


@pytest.mark.parametrize(
    ("claim_changes", "policy_changes", "message"),
    [
        ({"issuer": "https://attacker.test"}, {}, "issuer"),
        ({"audience": "another-api"}, {}, "audience"),
        ({"subject": "unknown-service"}, {}, "allowlist"),
        ({"scopes": ("finance:portfolio:write",)}, {}, "allowlist"),
        ({"expires_at": STAMP - 60}, {}, "expired"),
        ({"not_before": STAMP + 60}, {}, "not active"),
        ({"issued_at": STAMP + 60}, {}, "future"),
        ({"expires_at": STAMP + 600}, {}, "lifetime"),
    ],
)
def test_rejects_untrusted_or_overprivileged_claims(claim_changes, policy_changes, message):
    with pytest.raises(ServiceAuthorizationError, match=message):
        authorize_finance_service(claims(**claim_changes), policy(**policy_changes), now=NOW)


def test_rejects_non_demo_environment():
    with pytest.raises(ServiceAuthorizationError, match="Demo environment"):
        claims(environment="live")


def test_claim_contract_has_no_tenant_or_account_identity_fields():
    names = {field.name for field in fields(VerifiedServiceTokenClaims)}
    assert "tenant_id" not in names
    assert "account_id" not in names
    assert "account_reference" not in names
    assert "bearer_token" not in names


def test_rejects_duplicate_scopes_and_inconsistent_times():
    with pytest.raises(ServiceAuthorizationError, match="Duplicate"):
        claims(scopes=(FINANCE_PORTFOLIO_READ, FINANCE_PORTFOLIO_READ))
    with pytest.raises(ServiceAuthorizationError, match="inconsistent"):
        claims(issued_at=STAMP + 10, expires_at=STAMP)


def test_rejects_unverified_claim_object():
    with pytest.raises(TypeError, match="trusted verifier"):
        authorize_finance_service({"subject": "trading-bridge-demo"}, policy(), now=NOW)
