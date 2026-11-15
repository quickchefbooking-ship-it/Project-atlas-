import sqlite3

import pytest
from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.tenant_reasoning_audit import (
    TenantReasoningAuditRepository, initialize_reasoning_audit_schema,
)


SCOPES = frozenset({"conversations:read", "conversations:write"})


def principal(subject="alice", tenant="tenant-a"):
    return RequestPrincipal("https://issuer.example.test", subject, tenant, True, SCOPES)


def database(tmp_path):
    db = sqlite3.connect(tmp_path / "audit.sqlite")
    db.row_factory = sqlite3.Row
    initialize_reasoning_audit_schema(db)
    return db


def test_audit_stores_hashes_not_raw_content_and_chains_records(tmp_path):
    db = database(tmp_path)
    repo = TenantReasoningAuditRepository(db, principal())
    first = repo.append(
        conversation_id="chat-1", request_text="private prompt",
        response_text="private answer", context_text="system policy",
        provider="fixture", model="fixture-v1",
        evidence=[{"document_id": "doc-1", "url": "https://example.test/doc",
                   "content_sha256": "a" * 64, "trust_level": "curated"}],
    )
    second = repo.append(
        conversation_id="chat-1", request_text="second prompt",
        response_text="second answer", context_text="system policy",
        provider="fixture", model="fixture-v1", evidence=[],
    )
    assert first.previous_hash == "0" * 64
    assert second.previous_hash == first.record_hash
    assert first.request_sha256 != "private prompt"
    raw = db.execute("SELECT * FROM tenant_professor_reasoning_audit").fetchall()
    assert "private prompt" not in str([dict(row) for row in raw])
    assert len(repo.list("chat-1")) == 2


def test_audit_is_owner_and_tenant_isolated(tmp_path):
    db = database(tmp_path)
    TenantReasoningAuditRepository(db, principal()).append(
        conversation_id="chat-1", request_text="q", response_text="a",
        context_text="ctx", provider="fixture", model="v1", evidence=[],
    )
    assert TenantReasoningAuditRepository(db, principal("bob")).list("chat-1") == ()
    assert TenantReasoningAuditRepository(db, principal("alice", "tenant-b")).list("chat-1") == ()


def test_audit_records_are_append_only(tmp_path):
    db = database(tmp_path)
    repo = TenantReasoningAuditRepository(db, principal())
    record = repo.append(
        conversation_id="chat-1", request_text="q", response_text="a",
        context_text="ctx", provider="fixture", model="v1", evidence=[],
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE tenant_professor_reasoning_audit SET model='tampered' WHERE audit_id=?", (record.audit_id,))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM tenant_professor_reasoning_audit WHERE audit_id=?", (record.audit_id,))


def test_audit_rejects_unbounded_metadata(tmp_path):
    db = database(tmp_path)
    repo = TenantReasoningAuditRepository(db, principal())
    with pytest.raises(ValueError):
        repo.append(conversation_id="chat-1", request_text="q", response_text="a",
                    context_text="ctx", provider="p" * 65, model="v1", evidence=[])


def test_chain_verifier_accepts_valid_chain_and_detects_tampering(tmp_path):
    db = database(tmp_path)
    repo = TenantReasoningAuditRepository(db, principal())
    first = repo.append(
        conversation_id="chat-1", request_text="q1", response_text="a1",
        context_text="ctx", provider="fixture", model="v1", evidence=[],
    )
    repo.append(
        conversation_id="chat-2", request_text="q2", response_text="a2",
        context_text="ctx", provider="fixture", model="v1", evidence=[],
    )
    assert repo.verify_chain() == {
        "valid": True, "records_checked": 2, "broken_audit_ids": [],
        "scope": "current_tenant_and_owner", "raw_content_checked": False,
    }
    db.execute(
        "DROP TRIGGER professor_reasoning_audit_no_update"
    )
    db.execute(
        "UPDATE tenant_professor_reasoning_audit SET model='tampered' WHERE audit_id=?",
        (first.audit_id,),
    )
    result = repo.verify_chain()
    assert result["valid"] is False
    assert result["broken_audit_ids"] == [first.audit_id]


def test_audit_records_safe_reasoning_decisions_and_hashes_them(tmp_path):
    db = database(tmp_path)
    repo = TenantReasoningAuditRepository(db, principal())
    record = repo.append(
        conversation_id="chat-meta", request_text="q", response_text="a",
        context_text="ctx", provider="fixture", model="v1", evidence=[],
        metadata={
            "status": "ready", "step_count": 2, "critique_accepted": True,
            "goal_coverage": 0.8, "action_boundary": "information_only",
            "execution_enabled": False,
        },
    )
    assert record.metadata["step_count"] == 2
    assert record.metadata["critique_accepted"] is True
    assert repo.verify_chain()["valid"] is True
    with pytest.raises(ValueError):
        repo.append(
            conversation_id="chat-meta", request_text="q", response_text="a",
            context_text="ctx", provider="fixture", model="v1", evidence=[],
            metadata={"execution_enabled": True},
        )
    db.execute("DROP TRIGGER professor_reasoning_audit_no_update")
    db.execute(
        "UPDATE tenant_professor_reasoning_audit SET metadata_json='{}' WHERE audit_id=?",
        (record.audit_id,),
    )
    assert repo.verify_chain()["valid"] is False


def test_audit_schema_migrates_existing_database_without_breaking_old_chain(tmp_path):
    db = sqlite3.connect(tmp_path / "legacy.sqlite")
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE tenant_professor_reasoning_audit (
      audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
      tenant_id TEXT NOT NULL, owner_key TEXT NOT NULL, conversation_id TEXT NOT NULL,
      request_sha256 TEXT NOT NULL, response_sha256 TEXT NOT NULL, context_sha256 TEXT NOT NULL,
      provider TEXT NOT NULL, model TEXT NOT NULL, evidence_json TEXT NOT NULL,
      previous_hash TEXT NOT NULL, record_hash TEXT NOT NULL UNIQUE,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    initialize_reasoning_audit_schema(db)
    repo = TenantReasoningAuditRepository(db, principal())
    assert repo.verify_chain()["valid"] is True
