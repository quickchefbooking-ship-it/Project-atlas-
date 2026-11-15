import sqlite3

import pytest

from atlas_engine.account_identity import (
    AccountAlreadyExists,
    AccountNotFound,
    Argon2idCredentialHasher,
    InvalidCredential,
    SQLiteAccountRepository,
    normalize_email,
)


@pytest.fixture
def account_store(tmp_path):
    repo = SQLiteAccountRepository(str(tmp_path / "isolated-accounts.sqlite"))
    repo.initialize()
    return repo


def test_email_is_normalized_and_validated():
    assert normalize_email("  Alice.Example@Example.COM ") == "alice.example@example.com"
    with pytest.raises(ValueError):
        normalize_email("not-an-email")


def test_argon2id_hashes_password_without_reversible_storage():
    hasher = Argon2idCredentialHasher(time_cost=1, memory_cost=19456, parallelism=1)
    encoded = hasher.hash("correct horse battery staple")
    assert encoded.startswith("$argon2id$")
    assert "correct horse battery staple" not in encoded
    assert hasher.verify(encoded, "correct horse battery staple") is True
    assert hasher.verify(encoded, "wrong password value") is False


def test_hashing_rejects_short_or_unbounded_passwords():
    hasher = Argon2idCredentialHasher(time_cost=1, memory_cost=19456, parallelism=1)
    with pytest.raises(ValueError):
        hasher.hash("short")
    with pytest.raises(ValueError):
        hasher.hash("x" * 1025)


def test_pending_account_is_not_authenticatable_until_activated(account_store):
    account = account_store.create_pending_account("Alice@Example.com", "a sufficiently long password")
    assert account.email == "alice@example.com"
    assert account.status == "pending_verification"
    with pytest.raises(InvalidCredential):
        account_store.verify_password("alice@example.com", "a sufficiently long password")


def test_active_account_can_authenticate_and_duplicate_email_is_rejected(account_store):
    account = account_store.create_pending_account("Alice@Example.com", "a sufficiently long password")
    account_store.set_account_status(account.account_id, "active")
    verified = account_store.verify_password("ALICE@example.com", "a sufficiently long password")
    assert verified.account_id == account.account_id
    assert verified.status == "active"
    with pytest.raises(AccountAlreadyExists):
        account_store.create_pending_account("alice@example.com", "another sufficiently long password")


def test_unknown_and_wrong_password_use_same_generic_error(account_store):
    account_store.create_pending_account("alice@example.com", "a sufficiently long password")
    with pytest.raises(InvalidCredential, match="Credential verification failed"):
        account_store.verify_password("unknown@example.com", "a sufficiently long password")
    with pytest.raises(InvalidCredential, match="Credential verification failed"):
        account_store.verify_password("alice@example.com", "incorrect password value")


def test_suspended_and_closed_accounts_cannot_authenticate(account_store):
    account = account_store.create_pending_account("alice@example.com", "a sufficiently long password")
    account_store.set_account_status(account.account_id, "active")
    account_store.set_account_status(account.account_id, "suspended")
    with pytest.raises(InvalidCredential):
        account_store.verify_password("alice@example.com", "a sufficiently long password")
    account_store.set_account_status(account.account_id, "closed")
    with pytest.raises(InvalidCredential):
        account_store.verify_password("alice@example.com", "a sufficiently long password")


def test_missing_account_status_target_is_rejected(account_store):
    with pytest.raises(AccountNotFound):
        account_store.set_account_status("missing-account", "active")


def test_account_schema_is_separate_and_does_not_store_plaintext_password(account_store):
    account_store.create_pending_account("alice@example.com", "a sufficiently long password")
    conn = sqlite3.connect(account_store.database_path)
    try:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert names == {"atlas_accounts", "atlas_account_tokens"}
        row = conn.execute("SELECT password_hash FROM atlas_accounts").fetchone()
        assert row[0].startswith("$argon2id$")
        assert "sufficiently long password" not in row[0]
    finally:
        conn.close()


from datetime import timedelta


def test_email_verification_token_is_hashed_single_use_and_activates_account(account_store):
    account = account_store.create_pending_account("alice@example.com", "a sufficiently long password")
    token = account_store.issue_email_verification_token(account.account_id)
    conn = sqlite3.connect(account_store.database_path)
    try:
        stored_hash = conn.execute(
            "SELECT token_hash FROM atlas_account_tokens WHERE account_id=?",
            (account.account_id,),
        ).fetchone()[0]
        assert stored_hash != token
        assert len(stored_hash) == 64
    finally:
        conn.close()

    activated = account_store.verify_email(token)
    assert activated.status == "active"
    assert account_store.verify_password("alice@example.com", "a sufficiently long password").account_id == account.account_id
    with pytest.raises(InvalidCredential):
        account_store.verify_email(token)


def test_reissuing_verification_invalidates_previous_token(account_store):
    account = account_store.create_pending_account("alice@example.com", "a sufficiently long password")
    first = account_store.issue_email_verification_token(account.account_id)
    second = account_store.issue_email_verification_token(account.account_id)
    with pytest.raises(InvalidCredential):
        account_store.verify_email(first)
    assert account_store.verify_email(second).status == "active"


def test_expired_email_verification_token_is_rejected(account_store):
    account = account_store.create_pending_account("alice@example.com", "a sufficiently long password")
    with pytest.raises(ValueError):
        account_store.issue_email_verification_token(account.account_id, lifetime=timedelta(seconds=0))
    token = account_store.issue_email_verification_token(account.account_id, lifetime=timedelta(seconds=1))
    conn = sqlite3.connect(account_store.database_path)
    try:
        conn.execute(
            "UPDATE atlas_account_tokens SET expires_at='2000-01-01T00:00:00+00:00' WHERE token_hash=?",
            (__import__("hashlib").sha256(token.encode()).hexdigest(),),
        )
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(InvalidCredential):
        account_store.verify_email(token)


def test_password_recovery_is_generic_for_unknown_account_and_single_use(account_store):
    assert account_store.issue_password_recovery_token("unknown@example.com") is None
    account = account_store.create_pending_account("alice@example.com", "a sufficiently long password")
    verification = account_store.issue_email_verification_token(account.account_id)
    account_store.verify_email(verification)
    token = account_store.issue_password_recovery_token("ALICE@example.com")
    assert token is not None
    account_store.reset_password(token, "a completely new secure password")
    assert account_store.verify_password("alice@example.com", "a completely new secure password").account_id == account.account_id
    with pytest.raises(InvalidCredential):
        account_store.verify_password("alice@example.com", "a sufficiently long password")
    with pytest.raises(InvalidCredential):
        account_store.reset_password(token, "yet another secure password")


def test_password_reset_invalidates_all_outstanding_account_tokens(account_store):
    account = account_store.create_pending_account("alice@example.com", "a sufficiently long password")
    account_store.verify_email(account_store.issue_email_verification_token(account.account_id))
    first = account_store.issue_password_recovery_token("alice@example.com")
    second = account_store.issue_password_recovery_token("alice@example.com")
    assert first and second
    account_store.reset_password(second, "a completely new secure password")
    with pytest.raises(InvalidCredential):
        account_store.reset_password(first, "another completely new password")


def test_recovery_token_cannot_be_issued_for_suspended_account(account_store):
    account = account_store.create_pending_account("alice@example.com", "a sufficiently long password")
    account_store.verify_email(account_store.issue_email_verification_token(account.account_id))
    account_store.set_account_status(account.account_id, "suspended")
    assert account_store.issue_password_recovery_token("alice@example.com") is None
