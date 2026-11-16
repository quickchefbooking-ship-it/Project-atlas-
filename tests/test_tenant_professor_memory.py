import sqlite3

import pytest

from atlas_engine.identity_policy import AuthorizationDenied, RequestPrincipal
from atlas_engine.tenant_professor_memory import (
    MemoryNotFound,
    TenantProfessorMemoryRepository,
    initialize_tenant_memory_schema,
)


@pytest.fixture
def memory_repos():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    initialize_tenant_memory_schema(db)
    scopes = frozenset({"memory:propose", "memory:approve", "memory:read", "memory:delete"})
    owner = RequestPrincipal("https://issuer.example.test", "alice", "tenant-a", True, scopes)
    other = RequestPrincipal("https://issuer.example.test", "bob", "tenant-a", True, scopes)
    other_tenant = RequestPrincipal("https://issuer.example.test", "alice", "tenant-b", True, scopes)
    return db, TenantProfessorMemoryRepository(db, owner), TenantProfessorMemoryRepository(db, other), TenantProfessorMemoryRepository(db, other_tenant)


def test_memory_is_not_retrievable_until_explicitly_approved(memory_repos):
    _db, owner, _other, _tenant = memory_repos
    owner.propose("p1", category="preference", title="Writing style", content="Use concise explanations.")
    assert owner.retrieve("concise explanations") == ()
    owner.decide("p1", decision="approved", rationale="User confirmed this is useful.")
    result = owner.retrieve("concise explanations")
    assert len(result) == 1
    assert result[0]["proposal_id"] == "p1"


def test_memory_is_owner_and_tenant_isolated(memory_repos):
    _db, owner, other, other_tenant = memory_repos
    owner.propose("private", category="context", title="Project", content="Atlas core architecture")
    owner.decide("private", decision="approved")
    assert other.retrieve("Atlas architecture") == ()
    assert other_tenant.retrieve("Atlas architecture") == ()
    with pytest.raises(MemoryNotFound):
        other.decide("private", decision="approved")


def test_memory_requires_scopes(memory_repos):
    db, _owner, _other, _tenant = memory_repos
    no_approval = TenantProfessorMemoryRepository(
        db, RequestPrincipal("issuer", "reviewer", "tenant-a", True, frozenset({"memory:read"}))
    )
    with pytest.raises(AuthorizationDenied):
        no_approval.decide("missing", decision="approved")


def test_memory_decision_is_single_use_and_recorded(memory_repos):
    db, owner, _other, _tenant = memory_repos
    owner.propose("p2", category="project", title="Atlas", content="Keep the brain as the priority.")
    owner.decide("p2", decision="approved")
    with pytest.raises(ValueError, match="pending"):
        owner.decide("p2", decision="rejected")
    assert db.execute("SELECT COUNT(*) FROM tenant_professor_memory_decisions").fetchone()[0] == 1


def test_memory_rejects_unbounded_input_and_retention(memory_repos):
    _db, owner, _other, _tenant = memory_repos
    with pytest.raises(ValueError):
        owner.propose("bad", category="x", title="x", content="y", retention_days=0)
    with pytest.raises(ValueError):
        owner.propose("bad2", category="x", title="x", content="y" * 2001)


def test_rejected_memory_is_never_retrieved(memory_repos):
    _db, owner, _other, _tenant = memory_repos
    owner.propose("no", category="preference", title="No", content="Do not retain this.")
    owner.decide("no", decision="rejected")
    assert owner.retrieve("retain this") == ()


def test_memory_deletion_removes_content_and_decisions(memory_repos):
    db, owner, _other, _tenant = memory_repos
    owner.propose("delete", category="context", title="Private", content="Remove this content.")
    owner.decide("delete", decision="approved")
    owner.delete("delete")
    assert owner.retrieve("Remove content") == ()
    assert db.execute("SELECT COUNT(*) FROM tenant_professor_memory_proposals").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM tenant_professor_memory_decisions").fetchone()[0] == 0


def test_memory_requires_verified_active_membership(memory_repos):
    db, _owner, _other, _tenant = memory_repos
    inactive = TenantProfessorMemoryRepository(
        db, RequestPrincipal("issuer", "inactive", "tenant-a", False, frozenset({"memory:read"}))
    )
    with pytest.raises(AuthorizationDenied):
        inactive.retrieve("anything")

def test_memory_retrieval_normalizes_punctuation_and_weights_title_matches(memory_repos):
    db, owner, _other, _tenant = memory_repos
    owner.propose("title-hit", category="preference", title="Concise answer style",
                  content="Use plain words.")
    owner.decide("title-hit", decision="approved")
    owner.propose("body-hit", category="context", title="General note",
                  content="Concise answer style is sometimes useful.")
    owner.decide("body-hit", decision="approved")
    results = owner.retrieve("concise, answer!")
    assert [item["proposal_id"] for item in results] == ["title-hit", "body-hit"]
    assert results[0]["matched_terms"] == ["answer", "concise"]

def test_expired_approved_memory_is_not_retrieved(memory_repos):
    db, owner, _other, _tenant = memory_repos
    owner.propose("expired", category="preference", title="Concise answers",
                  content="Use concise answers.")
    owner.decide("expired", decision="approved")
    db.execute("UPDATE tenant_professor_memory_proposals SET expires_at=? WHERE proposal_id=?",
               ("2000-01-01T00:00:00+00:00", "expired"))
    assert owner.retrieve("concise answers") == ()

def test_expiry_cleanup_removes_only_current_owners_expired_records(memory_repos):
    db, owner, other, _tenant = memory_repos
    owner.propose("expired-owner", category="context", title="Old owner note", content="Expired owner content.")
    owner.decide("expired-owner", decision="approved")
    owner.propose("live-owner", category="context", title="Current owner note", content="Keep this content.")
    other.propose("expired-other", category="context", title="Other owner note", content="Other owner's content.")
    db.execute(
        "UPDATE tenant_professor_memory_proposals SET expires_at=? WHERE proposal_id IN (?,?)",
        ("2000-01-01T00:00:00+00:00", "expired-owner", "expired-other"),
    )
    assert owner.purge_expired() == 1
    assert owner.list_proposals(status="all") == tuple(
        item for item in owner.list_proposals(status="all") if item["proposal_id"] == "live-owner"
    )
    assert db.execute(
        "SELECT COUNT(*) FROM tenant_professor_memory_decisions WHERE proposal_id='expired-owner'"
    ).fetchone()[0] == 0
    assert other.list_proposals(status="all")[0]["proposal_id"] == "expired-other"


def test_expiry_cleanup_requires_delete_scope_and_bounded_limit(memory_repos):
    db, _owner, _other, _tenant = memory_repos
    reader = TenantProfessorMemoryRepository(
        db, RequestPrincipal("issuer", "reader", "tenant-a", True, frozenset({"memory:read"}))
    )
    with pytest.raises(AuthorizationDenied):
        reader.purge_expired()
    owner_without_delete = TenantProfessorMemoryRepository(
        db, RequestPrincipal("issuer", "no-delete", "tenant-a", True, frozenset({"memory:read"}))
    )
    with pytest.raises(AuthorizationDenied):
        owner_without_delete.purge_expired()


def test_memory_retrieval_prefers_more_recent_record_when_relevance_is_equal(memory_repos):
    db, owner, _other, _tenant = memory_repos
    owner.propose("older", category="project", title="Atlas project notes", content="Architecture context.")
    owner.decide("older", decision="approved")
    owner.propose("newer", category="project", title="Atlas project notes", content="Updated architecture context.")
    owner.decide("newer", decision="approved")
    db.execute(
        "UPDATE tenant_professor_memory_proposals SET created_at=? WHERE proposal_id=?",
        ("2026-01-01T00:00:00+00:00", "older"),
    )
    db.execute(
        "UPDATE tenant_professor_memory_proposals SET created_at=? WHERE proposal_id=?",
        ("2026-02-01T00:00:00+00:00", "newer"),
    )
    results = owner.retrieve("Atlas project", limit=2)
    assert [item["proposal_id"] for item in results] == ["newer", "older"]
    assert results[0]["matched_fields"] == ["title", "category"]


def test_memory_retrieval_supports_unicode_terms_and_explains_matches(memory_repos):
    _db, owner, _other, _tenant = memory_repos
    owner.propose("unicode", category="preference", title="Café préféré",
                  content="Répondre avec des explications claires.")
    owner.decide("unicode", decision="approved")
    results = owner.retrieve("café préféré")
    assert len(results) == 1
    assert results[0]["proposal_id"] == "unicode"
    assert results[0]["matched_terms"] == ["café", "préféré"]
    assert results[0]["matched_fields"] == ["title"]


def test_confirmed_supersession_hides_old_memory_and_keeps_audit(memory_repos):
    db, owner, _other, _tenant = memory_repos
    owner.propose("old-pref", category="preference", title="Answer style",
                  content="Give detailed explanations.")
    owner.decide("old-pref", decision="approved")
    owner.propose("new-pref", category="preference", title="Answer style",
                  content="Give concise explanations.")
    owner.decide("new-pref", decision="approved")
    assert len(owner.retrieve("explanations", limit=5)) == 2
    owner.confirm_supersession(
        "old-pref", "new-pref", confirmed=True,
        rationale="Owner confirmed the concise preference replaces the old one.",
    )
    results = owner.retrieve("explanations", limit=5)
    assert [item["proposal_id"] for item in results] == ["new-pref"]
    history = owner.list_supersessions()
    assert len(history) == 1
    assert history[0]["prior_proposal_id"] == "old-pref"
    assert history[0]["replacement_proposal_id"] == "new-pref"
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute(
            "UPDATE tenant_professor_memory_supersessions SET rationale='changed'"
        )


def test_supersession_requires_explicit_confirmation_and_approval_scope(memory_repos):
    db, owner, _other, _tenant = memory_repos
    owner.propose("old", category="preference", title="Style", content="Old style.")
    owner.decide("old", decision="approved")
    owner.propose("new", category="preference", title="Style", content="New style.")
    owner.decide("new", decision="approved")
    with pytest.raises(ValueError, match="explicit owner confirmation"):
        owner.confirm_supersession("old", "new", confirmed=False)
    reader = TenantProfessorMemoryRepository(
        db, RequestPrincipal("https://issuer.example.test", "reader", "tenant-a",
                             True, frozenset({"memory:read"}))
    )
    with pytest.raises(AuthorizationDenied):
        reader.confirm_supersession("old", "new", confirmed=True)


def test_supersession_rejects_cross_owner_and_invalid_records(memory_repos):
    _db, owner, other, _tenant = memory_repos
    owner.propose("old", category="preference", title="Style", content="Old style.")
    owner.decide("old", decision="approved")
    owner.propose("new", category="preference", title="Style", content="New style.")
    owner.decide("new", decision="approved")
    with pytest.raises(MemoryNotFound):
        other.confirm_supersession("old", "new", confirmed=True)
    with pytest.raises(ValueError, match="cannot supersede itself"):
        owner.confirm_supersession("old", "old", confirmed=True)
    with pytest.raises(ValueError, match="already superseded or linked"):
        owner.confirm_supersession("old", "new", confirmed=True)
    owner.propose("pending", category="preference", title="Style", content="Pending style.")
    with pytest.raises(ValueError, match="approved, unexpired"):
        owner.confirm_supersession("new", "pending", confirmed=True)


def test_deleting_memory_removes_linked_supersession_metadata(memory_repos):
    db, owner, _other, _tenant = memory_repos
    owner.propose("old", category="preference", title="Style", content="Old style.")
    owner.decide("old", decision="approved")
    owner.propose("new", category="preference", title="Style", content="New style.")
    owner.decide("new", decision="approved")
    owner.confirm_supersession("old", "new", confirmed=True)
    owner.delete("old")
    assert owner.list_supersessions() == ()
    assert db.execute("SELECT COUNT(*) FROM tenant_professor_memory_supersessions").fetchone()[0] == 0
