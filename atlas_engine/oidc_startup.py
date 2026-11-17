"""Fail-closed startup composition for hosted Atlas OIDC browser login.

The factory reads only explicit deployment-owned settings. Missing settings leave
login unconfigured; invalid complete settings raise before any provider request.
It never discovers providers, creates accounts, links identities, or provisions
tenant memberships.
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping

from .account_identity import SQLiteAccountRepository
from .oidc_account_link import OIDCAccountLinkService, SQLiteOIDCAccountLinkRepository
from .oidc_browser_login import OIDCBrowserLoginService
from .oidc_browser_routes import OIDCBrowserLoginInitiator
from .oidc_contract import OIDCProviderConfig
from .oidc_http_token_exchange import HTTPSOIDCAuthorizationCodeExchanger
from .oidc_id_token_verifier import PyJWTIDTokenVerifier
from .oidc_login_session import OIDCLoginSessionService
from .oidc_login_transaction import SQLiteOIDCLoginTransactionStore
from .session_identity import SQLiteSessionRepository
from .tenant_membership import SQLiteMembershipRegistry


OIDC_BROWSER_LOGIN_REQUIRED_SETTINGS = (
    "ATLAS_OIDC_ISSUER",
    "ATLAS_OIDC_AUDIENCE",
    "ATLAS_OIDC_JWKS_URI",
    "ATLAS_OIDC_ALLOWED_ALGORITHMS",
    "ATLAS_MEMBERSHIP_DB_PATH",
    "ATLAS_OIDC_AUTHORIZATION_ENDPOINT",
    "ATLAS_OIDC_TOKEN_ENDPOINT",
    "ATLAS_OIDC_CLIENT_ID",
    "ATLAS_OIDC_REDIRECT_URI",
    "ATLAS_ACCOUNT_DB_PATH",
    "ATLAS_OIDC_LOGIN_TRANSACTION_DB_PATH",
    "ATLAS_OIDC_LOGIN_TRANSACTION_KEY_HEX",
)


def _canonical_database_paths(
    *,
    core_database_path: str | None,
    tenant_database_path: str | None,
    membership_database_path: str,
    account_database_path: str,
    transaction_database_path: str,
) -> dict[str, str]:
    """Require dedicated file-backed stores and reject path aliasing."""
    raw_paths = {
        "core": core_database_path,
        "tenant": tenant_database_path,
        "membership": membership_database_path,
        "account": account_database_path,
        "login transaction": transaction_database_path,
    }
    resolved: dict[str, str] = {}
    owners: dict[str, str] = {}
    for label, raw_path in raw_paths.items():
        if raw_path is None:
            continue
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"{label} database path must be non-empty text.")
        if raw_path == ":memory:":
            if label in {"membership", "account", "login transaction"}:
                raise ValueError(f"{label} storage must use a dedicated file-backed database.")
            continue
        canonical = os.path.realpath(raw_path)
        previous = owners.get(canonical)
        if previous is not None:
            raise ValueError(
                f"{label} storage must use a separate database from {previous} storage."
            )
        owners[canonical] = label
        resolved[label] = canonical
    return resolved


def build_oidc_browser_login_services(
    environ: Mapping[str, str] | None = None,
    *,
    core_database_path: str | None = None,
    tenant_database_path: str | None = None,
    membership_registry: SQLiteMembershipRegistry | None = None,
) -> tuple[OIDCBrowserLoginInitiator | None, OIDCBrowserLoginService | None]:
    """Build matching OIDC login and callback services, or leave both disabled.

    All required settings are checked before constructing or initializing any
    database. Account/session storage and encrypted one-time login transactions
    must be separate from core, tenant and membership storage. Existing
    membership repositories may be reused, but no memberships or account links
    are created by this factory.
    """
    settings = os.environ if environ is None else environ
    values = {name: settings.get(name) for name in OIDC_BROWSER_LOGIN_REQUIRED_SETTINGS}
    if any(not isinstance(value, str) or not value for value in values.values()):
        return None, None

    key_text = values["ATLAS_OIDC_LOGIN_TRANSACTION_KEY_HEX"]
    if re.fullmatch(r"[0-9a-fA-F]{64}", key_text) is None:
        raise ValueError("OIDC login transaction key must be exactly 32 bytes encoded as 64 hexadecimal characters.")
    transaction_key = bytes.fromhex(key_text)

    paths = _canonical_database_paths(
        core_database_path=core_database_path,
        tenant_database_path=tenant_database_path,
        membership_database_path=values["ATLAS_MEMBERSHIP_DB_PATH"],
        account_database_path=values["ATLAS_ACCOUNT_DB_PATH"],
        transaction_database_path=values["ATLAS_OIDC_LOGIN_TRANSACTION_DB_PATH"],
    )
    membership_path = paths["membership"]
    account_path = paths["account"]
    transaction_path = paths["login transaction"]

    if membership_registry is not None:
        if not isinstance(membership_registry, SQLiteMembershipRegistry):
            raise TypeError("A trusted SQLiteMembershipRegistry is required.")
        if os.path.realpath(membership_registry.database_path) != membership_path:
            raise ValueError("The supplied membership registry must use ATLAS_MEMBERSHIP_DB_PATH.")
        memberships = membership_registry
    else:
        memberships = SQLiteMembershipRegistry(membership_path)

    algorithms = frozenset(
        item.strip()
        for item in values["ATLAS_OIDC_ALLOWED_ALGORITHMS"].split(",")
        if item.strip()
    )
    provider_config = OIDCProviderConfig(
        issuer=values["ATLAS_OIDC_ISSUER"],
        audience=values["ATLAS_OIDC_AUDIENCE"],
        jwks_uri=values["ATLAS_OIDC_JWKS_URI"],
        allowed_algorithms=algorithms,
    )

    client_id = values["ATLAS_OIDC_CLIENT_ID"]
    redirect_uri = values["ATLAS_OIDC_REDIRECT_URI"]
    accounts = SQLiteAccountRepository(account_path)
    sessions = SQLiteSessionRepository(account_path)
    transactions = SQLiteOIDCLoginTransactionStore(
        transaction_path,
        transaction_key,
    )
    account_link_repository = SQLiteOIDCAccountLinkRepository(accounts)
    account_links = OIDCAccountLinkService(account_link_repository, transactions)
    login_sessions = OIDCLoginSessionService(account_links, sessions, memberships)
    exchanger = HTTPSOIDCAuthorizationCodeExchanger(
        token_endpoint=values["ATLAS_OIDC_TOKEN_ENDPOINT"],
        client_id=client_id,
        redirect_uri=redirect_uri,
        client_secret=settings.get("ATLAS_OIDC_CLIENT_SECRET") or None,
    )
    id_token_verifier = PyJWTIDTokenVerifier(provider_config, client_id)
    callback = OIDCBrowserLoginService(
        transactions=transactions,
        exchanger=exchanger,
        id_token_verifier=id_token_verifier,
        login_sessions=login_sessions,
        redirect_uri=redirect_uri,
    )
    initiator = OIDCBrowserLoginInitiator(
        transactions=transactions,
        authorization_endpoint=values["ATLAS_OIDC_AUTHORIZATION_ENDPOINT"],
        client_id=client_id,
        redirect_uri=redirect_uri,
    )

    # Constructors above validate all fixed endpoints, key material, store
    # relationships and callback paths before any persistent schema is created.
    accounts.initialize()
    sessions.initialize()
    account_link_repository.initialize()
    transactions.initialize()
    memberships.initialize()

    return initiator, callback
