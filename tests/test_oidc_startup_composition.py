import sqlite3

import pytest

from atlas_engine.oidc_browser_login import OIDCBrowserLoginService
from atlas_engine.oidc_browser_routes import OIDCBrowserLoginInitiator
from atlas_engine.oidc_startup import build_oidc_browser_login_services
from atlas_engine.tenant_membership import SQLiteMembershipRegistry


def settings(tmp_path):
    return {
        "ATLAS_OIDC_ISSUER": "https://identity.example.test",
        "ATLAS_OIDC_AUDIENCE": "atlas-api",
        "ATLAS_OIDC_JWKS_URI": "https://identity.example.test/.well-known/jwks.json",
        "ATLAS_OIDC_ALLOWED_ALGORITHMS": "RS256",
        "ATLAS_MEMBERSHIP_DB_PATH": str(tmp_path / "membership.sqlite"),
        "ATLAS_OIDC_AUTHORIZATION_ENDPOINT": "https://identity.example.test/authorize",
        "ATLAS_OIDC_TOKEN_ENDPOINT": "https://identity.example.test/token",
        "ATLAS_OIDC_CLIENT_ID": "atlas-browser",
        "ATLAS_OIDC_REDIRECT_URI": "https://atlas.example.test/identity/callback",
        "ATLAS_ACCOUNT_DB_PATH": str(tmp_path / "accounts.sqlite"),
        "ATLAS_OIDC_LOGIN_TRANSACTION_DB_PATH": str(tmp_path / "login-transactions.sqlite"),
        "ATLAS_OIDC_LOGIN_TRANSACTION_KEY_HEX": "11" * 32,
    }


def table_count(database_path, table_name):
    connection = sqlite3.connect(database_path)
    try:
        return connection.execute(f"SELECT count(*) FROM {table_name}").fetchone()[0]
    finally:
        connection.close()


def test_missing_required_setting_leaves_both_services_disabled_without_database_side_effects(tmp_path):
    values = settings(tmp_path)
    values.pop("ATLAS_OIDC_TOKEN_ENDPOINT")

    initiator, callback = build_oidc_browser_login_services(
        values,
        core_database_path=str(tmp_path / "core.sqlite"),
        tenant_database_path=str(tmp_path / "tenant.sqlite"),
    )

    assert initiator is None
    assert callback is None
    assert not (tmp_path / "accounts.sqlite").exists()
    assert not (tmp_path / "membership.sqlite").exists()
    assert not (tmp_path / "login-transactions.sqlite").exists()


def test_complete_configuration_builds_matching_services_without_provisioning_accounts_or_memberships(tmp_path):
    values = settings(tmp_path)
    values["ATLAS_OIDC_CLIENT_SECRET"] = "a confidential test secret"

    initiator, callback = build_oidc_browser_login_services(
        values,
        core_database_path=str(tmp_path / "core.sqlite"),
        tenant_database_path=str(tmp_path / "tenant.sqlite"),
    )

    assert isinstance(initiator, OIDCBrowserLoginInitiator)
    assert isinstance(callback, OIDCBrowserLoginService)
    assert initiator.transactions is callback.transactions
    assert initiator.redirect_uri == callback.redirect_uri == values["ATLAS_OIDC_REDIRECT_URI"]
    assert initiator.authorization_endpoint == values["ATLAS_OIDC_AUTHORIZATION_ENDPOINT"]
    assert callback.exchanger.token_endpoint == values["ATLAS_OIDC_TOKEN_ENDPOINT"]
    assert callback.exchanger.client_id == values["ATLAS_OIDC_CLIENT_ID"]
    assert callback.exchanger.client_secret == "a confidential test secret"
    assert callback.login_sessions.sessions.database_path == values["ATLAS_ACCOUNT_DB_PATH"]
    assert callback.login_sessions.memberships.database_path == values["ATLAS_MEMBERSHIP_DB_PATH"]
    assert "a confidential test secret" not in repr(callback)

    # Startup creates only empty schemas. It does not create Atlas accounts,
    # external identity links, tenants or tenant memberships.
    assert table_count(values["ATLAS_ACCOUNT_DB_PATH"], "atlas_accounts") == 0
    assert table_count(values["ATLAS_ACCOUNT_DB_PATH"], "atlas_oidc_account_links") == 0
    assert table_count(values["ATLAS_MEMBERSHIP_DB_PATH"], "tenant_registry") == 0
    assert table_count(values["ATLAS_MEMBERSHIP_DB_PATH"], "tenant_memberships") == 0
    assert table_count(values["ATLAS_OIDC_LOGIN_TRANSACTION_DB_PATH"], "atlas_oidc_login_transactions") == 0


def test_existing_membership_registry_is_reused_only_when_database_path_matches(tmp_path):
    values = settings(tmp_path)
    registry = SQLiteMembershipRegistry(values["ATLAS_MEMBERSHIP_DB_PATH"])
    registry.initialize()

    initiator, callback = build_oidc_browser_login_services(
        values,
        membership_registry=registry,
    )

    assert initiator is not None
    assert callback is not None
    assert callback.login_sessions.memberships is registry


def test_account_and_transaction_databases_must_not_alias_other_storage(tmp_path):
    values = settings(tmp_path)
    values["ATLAS_ACCOUNT_DB_PATH"] = values["ATLAS_MEMBERSHIP_DB_PATH"]

    with pytest.raises(ValueError, match="separate database"):
        build_oidc_browser_login_services(
            values,
            core_database_path=str(tmp_path / "core.sqlite"),
            tenant_database_path=str(tmp_path / "tenant.sqlite"),
        )

    assert not (tmp_path / "membership.sqlite").exists()
    assert not (tmp_path / "login-transactions.sqlite").exists()


def test_invalid_transaction_key_fails_before_any_store_is_initialized(tmp_path):
    values = settings(tmp_path)
    values["ATLAS_OIDC_LOGIN_TRANSACTION_KEY_HEX"] = "not-a-32-byte-key"

    with pytest.raises(ValueError, match="32 bytes"):
        build_oidc_browser_login_services(values)

    assert not (tmp_path / "accounts.sqlite").exists()
    assert not (tmp_path / "membership.sqlite").exists()
    assert not (tmp_path / "login-transactions.sqlite").exists()


def test_redirect_must_be_the_fixed_identity_callback_before_store_initialization(tmp_path):
    values = settings(tmp_path)
    values["ATLAS_OIDC_REDIRECT_URI"] = "https://atlas.example.test/not-the-callback"

    with pytest.raises(ValueError, match="callback route"):
        build_oidc_browser_login_services(values)

    assert not (tmp_path / "accounts.sqlite").exists()
    assert not (tmp_path / "membership.sqlite").exists()
    assert not (tmp_path / "login-transactions.sqlite").exists()
