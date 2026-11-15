import hashlib
import sqlite3
from datetime import timedelta

import pytest

from atlas_engine.account_identity import InvalidCredential, SQLiteAccountRepository
from atlas_engine.session_identity import InvalidSession, SQLiteSessionRepository


@pytest.fixture
def identity(tmp_path):
    path = str(tmp_path / "atlas-identity.sqlite")
    accounts = SQLiteAccountRepository(path)
    accounts.initialize()
    account = accounts.create_pending_account("session@example.com", "a sufficiently long password")
    accounts.set_account_status(account.account_id, "active")
    sessions = SQLiteSessionRepository(path)
    sessions.initialize()
    return accounts, sessions, account


def test_session_secret_is_opaque_and_only_hash_is_stored(identity):
    _, sessions, account = identity
    issued = sessions.issue_session(account.account_id)
    assert len(issued.token) >= 40
    conn = sqlite3.connect(sessions.database_path)
    try:
        stored = conn.execute(
            "SELECT token_hash FROM atlas_sessions WHERE session_id=?", (issued.session_id,)
        ).fetchone()[0]
        assert stored == hashlib.sha256(issued.token.encode()).hexdigest()
        assert stored != issued.token
    finally:
        conn.close()
    assert sessions.validate_session(issued.token).account_id == account.account_id


def test_session_idle_expiry_is_extended_but_absolute_expiry_is_bounded(identity):
    _, sessions, account = identity
    issued = sessions.issue_session(account.account_id)
    validated = sessions.validate_session(issued.token)
    assert validated.idle_expires_at >= issued.idle_expires_at
    assert validated.absolute_expires_at == issued.absolute_expires_at


def test_expired_session_is_rejected_and_revoked(identity):
    _, sessions, account = identity
    issued = sessions.issue_session(account.account_id)
    conn = sqlite3.connect(sessions.database_path)
    try:
        conn.execute(
            "UPDATE atlas_sessions SET idle_expires_at='2000-01-01T00:00:00+00:00' WHERE session_id=?",
            (issued.session_id,),
        )
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(InvalidSession):
        sessions.validate_session(issued.token)
    with pytest.raises(InvalidSession):
        sessions.validate_session(issued.token)


def test_session_revocation_is_single_effect_and_blocks_validation(identity):
    _, sessions, account = identity
    issued = sessions.issue_session(account.account_id)
    assert sessions.revoke_session(issued.token) is True
    assert sessions.revoke_session(issued.token) is False
    with pytest.raises(InvalidSession):
        sessions.validate_session(issued.token)


def test_rotation_atomically_invalidates_old_token(identity):
    _, sessions, account = identity
    issued = sessions.issue_session(account.account_id)
    replacement = sessions.rotate_session(issued.token)
    assert replacement.account_id == account.account_id
    assert sessions.validate_session(replacement.token).session_id == replacement.session_id
    with pytest.raises(InvalidSession):
        sessions.validate_session(issued.token)
    with pytest.raises(InvalidSession):
        sessions.rotate_session(issued.token)


def test_suspended_account_cannot_use_existing_session(identity):
    accounts, sessions, account = identity
    issued = sessions.issue_session(account.account_id)
    accounts.set_account_status(account.account_id, "suspended")
    with pytest.raises(InvalidSession):
        sessions.validate_session(issued.token)
    with pytest.raises(InvalidSession):
        sessions.rotate_session(issued.token)


def test_revoke_all_sessions_covers_multiple_devices(identity):
    _, sessions, account = identity
    first = sessions.issue_session(account.account_id)
    second = sessions.issue_session(account.account_id)
    assert sessions.revoke_all_sessions(account.account_id) == 2
    for token in (first.token, second.token):
        with pytest.raises(InvalidSession):
            sessions.validate_session(token)


def test_session_timeouts_are_bounded():
    with pytest.raises(ValueError):
        SQLiteSessionRepository(":memory:", idle_timeout=timedelta(seconds=10))
    with pytest.raises(ValueError):
        SQLiteSessionRepository(":memory:", idle_timeout=timedelta(hours=2), absolute_timeout=timedelta(hours=1))
