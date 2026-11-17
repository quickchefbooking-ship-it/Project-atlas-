import time

import pytest

from atlas_engine.account_identity import Argon2idCredentialHasher, SQLiteAccountRepository
from atlas_engine.atlas_session_identity import ATLAS_IDENTITY_ISSUER, AtlasSessionIdentityService
from atlas_engine.identity_policy import AuthorizationDenied, RequestPrincipal
from atlas_engine.oidc_account_link import (
    IDENTITY_LINK_SCOPE,
    InactiveAtlasAccount,
    OIDCAccountLinkConflict,
    OIDCAccountLinkNotFound,
    OIDCAccountLinkService,
    SQLiteOIDCAccountLinkRepository,
)
from atlas_engine.oidc_id_token_verifier import VerifiedIDTokenClaims
from atlas_engine.oidc_login_transaction import (
    InvalidLoginTransaction,
    SQLiteOIDCLoginTransactionStore,
)
from atlas_engine.session_identity import SQLiteSessionRepository
from atlas_engine.tenant_membership import SQLiteMembershipRegistry


ISSUER = "https://idp.example.test/"
CLIENT_ID = "atlas-browser-client"
KEY = b"account-link-test-key-32-bytes!!"


@pytest.fixture
def setup(tmp_path):
    database = str(tmp_path / "atlas-identity.sqlite")
    accounts = SQLiteAccountRepository(
        database,
        Argon2idCredentialHasher(time_cost=1, memory_cost=19456, parallelism=1),
    )
    accounts.initialize()
    account = accounts.create_pending_account("alice@example.test", "a sufficiently long password")
    accounts.set_account_status(account.account_id, "active")

    sessions = SQLiteSessionRepository(database)
    sessions.initialize()
    memberships = SQLiteMembershipRegistry(str(tmp_path / "memberships.sqlite"))
    memberships.initialize()
    memberships.create_tenant("tenant-a", "Tenant A")
    memberships.provision_membership(
        ATLAS_IDENTITY_ISSUER,
        account.account_id,
        "tenant-a",
        {IDENTITY_LINK_SCOPE},
    )
    session_identity = AtlasSessionIdentityService(sessions, memberships)
    principal = session_identity.authenticate(sessions.issue_session(account.account_id).token)

    links = SQLiteOIDCAccountLinkRepository(accounts)
    links.initialize()
    transactions = SQLiteOIDCLoginTransactionStore(
        str(tmp_path / "login-transactions.sqlite"),
        KEY,
    )
    transactions.initialize()
    service = OIDCAccountLinkService(links, transactions)
    return accounts, sessions, memberships, principal, links, transactions, service


def verified_attempt(transactions, *, subject="provider-subject", nonce=None, issuer=ISSUER):
    start = transactions.begin()
    consumed = transactions.consume(start.state)
    claims = VerifiedIDTokenClaims(
        issuer=issuer,
        subject=subject,
        audiences=(CLIENT_ID,),
        expires_at=time.time() + 300,
        issued_at=time.time(),
        nonce=start.nonce if nonce is None else nonce,
    )
    return claims, consumed


def atlas_principal(sessions, memberships, account_id, *, scopes=frozenset({IDENTITY_LINK_SCOPE})):
    memberships.provision_membership(
        ATLAS_IDENTITY_ISSUER,
        account_id,
        "tenant-a",
        scopes,
    )
    service = AtlasSessionIdentityService(sessions, memberships)
    return service.authenticate(sessions.issue_session(account_id).token)


def create_active_account(accounts, email):
    account = accounts.create_pending_account(email, "another sufficiently long password")
    accounts.set_account_status(account.account_id, "active")
    return account


def test_link_requires_authenticated_atlas_account_and_nonce_then_resolves_exact_subject(setup):
    _, _, _, principal, _, transactions, service = setup
    claims, consumed = verified_attempt(transactions)

    linked = service.link_authenticated_account(principal, claims, consumed)

    assert linked.account_id == principal.subject
    assert linked.issuer == ISSUER
    assert linked.subject == "provider-subject"

    login_claims, login_transaction = verified_attempt(transactions)
    resolved = service.resolve_login_account(login_claims, login_transaction)
    assert resolved.account_id == principal.subject
    assert resolved.linked_at == linked.linked_at


def test_unknown_identity_is_not_auto_linked_even_when_email_matches(setup):
    _, _, _, _, _, transactions, service = setup
    claims, consumed = verified_attempt(transactions, subject="unlinked-provider-subject")

    with pytest.raises(OIDCAccountLinkNotFound):
        service.resolve_login_account(claims, consumed)


def test_external_identity_cannot_be_reassigned_to_another_atlas_account(setup):
    accounts, sessions, memberships, principal, _, transactions, service = setup
    claims, consumed = verified_attempt(transactions)
    service.link_authenticated_account(principal, claims, consumed)

    second = create_active_account(accounts, "bob@example.test")
    second_principal = atlas_principal(sessions, memberships, second.account_id)
    second_claims, second_transaction = verified_attempt(transactions)

    with pytest.raises(OIDCAccountLinkConflict):
        service.link_authenticated_account(second_principal, second_claims, second_transaction)


def test_one_atlas_account_cannot_link_two_subjects_from_the_same_issuer(setup):
    _, _, _, principal, _, transactions, service = setup
    first_claims, first_transaction = verified_attempt(transactions, subject="first-subject")
    service.link_authenticated_account(principal, first_claims, first_transaction)

    second_claims, second_transaction = verified_attempt(transactions, subject="second-subject")
    with pytest.raises(OIDCAccountLinkConflict):
        service.link_authenticated_account(principal, second_claims, second_transaction)


def test_same_identity_link_is_idempotent_for_the_same_account(setup):
    _, _, _, principal, _, transactions, service = setup
    first_claims, first_transaction = verified_attempt(transactions)
    first = service.link_authenticated_account(principal, first_claims, first_transaction)

    second_claims, second_transaction = verified_attempt(transactions)
    second = service.link_authenticated_account(principal, second_claims, second_transaction)

    assert second == first


def test_link_requires_dedicated_scope_and_an_atlas_session_principal(setup):
    _, _, _, principal, _, transactions, service = setup
    claims, consumed = verified_attempt(transactions)
    no_scope = RequestPrincipal(
        issuer=ATLAS_IDENTITY_ISSUER,
        subject=principal.subject,
        tenant_id=principal.tenant_id,
        membership_active=True,
        scopes=frozenset(),
    )
    with pytest.raises(AuthorizationDenied):
        service.link_authenticated_account(no_scope, claims, consumed)

    external_principal = RequestPrincipal(
        issuer=ISSUER,
        subject=principal.subject,
        tenant_id=principal.tenant_id,
        membership_active=True,
        scopes=frozenset({IDENTITY_LINK_SCOPE}),
    )
    claims, consumed = verified_attempt(transactions, subject="another-subject")
    with pytest.raises(AuthorizationDenied):
        service.link_authenticated_account(external_principal, claims, consumed)


def test_inactive_membership_and_suspended_account_cannot_link_or_login(setup):
    accounts, _, _, principal, _, transactions, service = setup
    inactive = RequestPrincipal(
        issuer=ATLAS_IDENTITY_ISSUER,
        subject=principal.subject,
        tenant_id=principal.tenant_id,
        membership_active=False,
        scopes=frozenset({IDENTITY_LINK_SCOPE}),
    )
    claims, consumed = verified_attempt(transactions)
    with pytest.raises(AuthorizationDenied):
        service.link_authenticated_account(inactive, claims, consumed)

    claims, consumed = verified_attempt(transactions, subject="suspended-account-identity")
    service.link_authenticated_account(principal, claims, consumed)
    accounts.set_account_status(principal.subject, "suspended")
    claims, consumed = verified_attempt(transactions, subject="suspended-account-identity")
    with pytest.raises(InactiveAtlasAccount):
        service.resolve_login_account(claims, consumed)


def test_nonce_mismatch_fails_closed_for_link_and_login(setup):
    _, _, _, principal, _, transactions, service = setup
    claims, consumed = verified_attempt(transactions, nonce="x" * 43)
    with pytest.raises(InvalidLoginTransaction):
        service.link_authenticated_account(principal, claims, consumed)

    claims, consumed = verified_attempt(transactions, subject="unknown", nonce="y" * 43)
    with pytest.raises(InvalidLoginTransaction):
        service.resolve_login_account(claims, consumed)


def test_unverified_claim_payload_is_not_accepted(setup):
    _, _, _, principal, _, transactions, service = setup
    _, consumed = verified_attempt(transactions)
    with pytest.raises(TypeError):
        service.link_authenticated_account(
            principal,
            {"issuer": ISSUER, "subject": "provider-subject"},
            consumed,
        )


def test_repository_requires_initialized_account_schema(tmp_path):
    accounts = SQLiteAccountRepository(str(tmp_path / "uninitialized.sqlite"))
    links = SQLiteOIDCAccountLinkRepository(accounts)
    with pytest.raises(RuntimeError, match="account repository"):
        links.initialize()


def test_provider_subjects_are_case_sensitive_and_scoped_by_issuer(setup):
    _, _, _, principal, _, transactions, service = setup
    claims, consumed = verified_attempt(transactions, subject="CaseSensitive")
    service.link_authenticated_account(principal, claims, consumed)

    other_issuer_claims, other_issuer_transaction = verified_attempt(
        transactions,
        subject="CaseSensitive",
        issuer="https://other-idp.example.test/",
    )
    linked = service.link_authenticated_account(
        principal,
        other_issuer_claims,
        other_issuer_transaction,
    )
    assert linked.issuer == "https://other-idp.example.test/"
    assert linked.subject == "CaseSensitive"
