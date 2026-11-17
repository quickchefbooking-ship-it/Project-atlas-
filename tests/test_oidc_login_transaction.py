import base64
import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from atlas_engine.oidc_login_transaction import (
    ConsumedLoginTransaction,
    InvalidLoginTransaction,
    SQLiteOIDCLoginTransactionStore,
)


KEY = b"atlas-test-login-key-32-bytes!!"


@pytest.fixture
def store(tmp_path):
    repository = SQLiteOIDCLoginTransactionStore(
        str(tmp_path / "identity" / "login-transactions.sqlite"),
        KEY,
    )
    repository.initialize()
    return repository


def test_begin_creates_s256_material_and_keeps_secrets_out_of_database(store):
    started = store.begin()

    expected_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(started.code_verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    assert started.code_challenge == expected_challenge
    assert 43 <= len(started.state) <= 128
    assert 43 <= len(started.nonce) <= 128
    assert 43 <= len(started.code_verifier) <= 128
    assert started.expires_at > 0

    conn = sqlite3.connect(store.database_path)
    try:
        row = conn.execute(
            """SELECT state_digest,nonce_digest,verifier_nonce,verifier_ciphertext
               FROM atlas_oidc_login_transactions"""
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    stored_bytes = b"|".join(
        value if isinstance(value, bytes) else str(value).encode("ascii")
        for value in row
    )
    assert started.state.encode("ascii") not in stored_bytes
    assert started.nonce.encode("ascii") not in stored_bytes
    assert started.code_verifier.encode("ascii") not in stored_bytes
    assert started.code_verifier not in repr(started)


def test_consume_returns_verifier_and_nonce_can_be_checked_once(store):
    started = store.begin()

    consumed = store.consume(started.state)

    assert isinstance(consumed, ConsumedLoginTransaction)
    assert consumed.code_verifier == started.code_verifier
    assert store.nonce_matches(consumed, started.nonce) is True
    assert store.nonce_matches(consumed, "x" * 43) is False
    assert started.code_verifier not in repr(consumed)
    with pytest.raises(InvalidLoginTransaction):
        store.consume(started.state)


def test_unknown_state_does_not_consume_another_transaction(store):
    started = store.begin()

    with pytest.raises(InvalidLoginTransaction):
        store.consume("x" * 43)

    consumed = store.consume(started.state)
    assert consumed.code_verifier == started.code_verifier


def test_expired_transaction_is_rejected(monkeypatch, tmp_path):
    now = [1_800_000_000]
    repository = SQLiteOIDCLoginTransactionStore(
        str(tmp_path / "expired.sqlite"),
        KEY,
        ttl_seconds=60,
        clock=lambda: now[0],
    )
    repository.initialize()
    started = repository.begin()
    now[0] = started.expires_at + 1

    with pytest.raises(InvalidLoginTransaction):
        repository.consume(started.state)
    with pytest.raises(InvalidLoginTransaction):
        repository.consume(started.state)


def test_concurrent_callback_replay_has_exactly_one_winner(store):
    started = store.begin()

    def consume_once():
        try:
            store.consume(started.state)
            return True
        except InvalidLoginTransaction:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: consume_once(), range(8)))

    assert sum(outcomes) == 1


def test_corrupt_verifier_ciphertext_is_consumed_and_cannot_be_replayed(store):
    started = store.begin()
    conn = sqlite3.connect(store.database_path)
    try:
        conn.execute(
            """UPDATE atlas_oidc_login_transactions
               SET verifier_ciphertext = ?""",
            (b"corrupted-ciphertext",),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(InvalidLoginTransaction):
        store.consume(started.state)
    with pytest.raises(InvalidLoginTransaction):
        store.consume(started.state)


@pytest.mark.parametrize("key", [b"", b"short", b"x" * 31, b"x" * 33, "x" * 32])
def test_store_requires_a_dedicated_32_byte_key(tmp_path, key):
    with pytest.raises(ValueError):
        SQLiteOIDCLoginTransactionStore(str(tmp_path / "bad-key.sqlite"), key)


@pytest.mark.parametrize("ttl", [True, 0, 59, 901, 300.0, "300"])
def test_transaction_ttl_is_strictly_bounded(tmp_path, ttl):
    with pytest.raises(ValueError):
        SQLiteOIDCLoginTransactionStore(
            str(tmp_path / "bad-ttl.sqlite"),
            KEY,
            ttl_seconds=ttl,
        )


def test_store_requires_file_backed_database(tmp_path):
    with pytest.raises(ValueError):
        SQLiteOIDCLoginTransactionStore(":memory:", KEY)
