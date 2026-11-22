from concurrent.futures import ThreadPoolExecutor

from atlas_engine.login_abuse_control import SQLiteLoginAbuseGuard


class Clock:
    def __init__(self, value=1_000_000.0):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def make_guard(tmp_path, clock, **kwargs):
    guard = SQLiteLoginAbuseGuard(
        str(tmp_path / "login-abuse.sqlite"),
        hmac_key=b"x" * 32,
        clock=clock,
        **kwargs,
    )
    guard.initialize()
    return guard


def test_throttles_account_and_network_after_configured_failures(tmp_path):
    clock = Clock()
    guard = make_guard(tmp_path, clock, max_failures=2, lockout_seconds=60)

    assert guard.check("person@example.test", "203.0.113.10").allowed
    assert guard.record_failure("person@example.test", "203.0.113.10").allowed
    decision = guard.record_failure("person@example.test", "203.0.113.10")

    assert not decision.allowed
    assert decision.retry_after_seconds == 60
    assert not guard.check("person@example.test", "203.0.113.10").allowed


def test_account_and_network_buckets_are_independent_and_network_survives_success(tmp_path):
    clock = Clock()
    guard = make_guard(tmp_path, clock, max_failures=1, lockout_seconds=30)

    guard.record_failure("first@example.test", "203.0.113.20")
    assert not guard.check("second@example.test", "203.0.113.20").allowed
    guard.record_success("first@example.test")
    assert not guard.check("second@example.test", "203.0.113.20").allowed
    assert guard.check("first@example.test", "203.0.113.21").allowed


def test_window_expiry_resets_failure_counter(tmp_path):
    clock = Clock()
    guard = make_guard(
        tmp_path, clock, max_failures=2, window_seconds=10, lockout_seconds=10
    )
    guard.record_failure("person@example.test", "198.51.100.4")
    clock.advance(11)
    assert guard.record_failure("person@example.test", "198.51.100.4").allowed


def test_lockout_expires_without_extending_on_checks(tmp_path):
    clock = Clock()
    guard = make_guard(tmp_path, clock, max_failures=1, lockout_seconds=20)
    guard.record_failure("person@example.test", "198.51.100.5")

    clock.advance(5)
    assert guard.check("person@example.test", "198.51.100.5").retry_after_seconds == 15
    clock.advance(15)
    assert guard.check("person@example.test", "198.51.100.5").allowed


def test_hmac_key_and_inputs_are_validated(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        SQLiteLoginAbuseGuard(str(tmp_path / "bad.sqlite"), hmac_key=b"short")
    guard = make_guard(tmp_path, Clock())
    with pytest.raises(ValueError):
        guard.check("", "203.0.113.1")


def test_database_does_not_store_raw_account_or_network_identifiers(tmp_path):
    import sqlite3

    guard = make_guard(tmp_path, Clock())
    guard.record_failure("private@example.test", "203.0.113.99")

    with sqlite3.connect(guard.database_path) as conn:
        values = repr(conn.execute(
            "SELECT bucket_key FROM atlas_login_abuse_buckets"
        ).fetchall())
    assert "private@example.test" not in values
    assert "203.0.113.99" not in values


def test_expired_buckets_can_be_purged(tmp_path):
    clock = Clock()
    guard = make_guard(tmp_path, clock, max_failures=3, window_seconds=10)
    guard.record_failure("person@example.test", "203.0.113.7")
    clock.advance(11)

    assert guard.purge_expired() == 2
    assert guard.check("person@example.test", "203.0.113.7").allowed


def test_concurrent_failures_cannot_bypass_account_or_network_threshold(tmp_path):
    clock = Clock()
    guard = make_guard(tmp_path, clock, max_failures=5, lockout_seconds=60)

    with ThreadPoolExecutor(max_workers=12) as pool:
        decisions = list(pool.map(
            lambda _: guard.record_failure("person@example.test", "192.0.2.44"),
            range(12),
        ))

    assert sum(decision.allowed for decision in decisions) == 4
    assert sum(not decision.allowed for decision in decisions) == 8
    assert not guard.check("person@example.test", "192.0.2.44").allowed


def test_concurrent_distinct_accounts_share_network_abuse_threshold(tmp_path):
    clock = Clock()
    guard = make_guard(tmp_path, clock, max_failures=5, lockout_seconds=60)

    with ThreadPoolExecutor(max_workers=12) as pool:
        decisions = list(pool.map(
            lambda index: guard.record_failure(
                f"person-{index}@example.test", "198.51.100.88"
            ),
            range(12),
        ))

    assert sum(decision.allowed for decision in decisions) == 4
    assert sum(not decision.allowed for decision in decisions) == 8
    assert not guard.check("another-account@example.test", "198.51.100.88").allowed
