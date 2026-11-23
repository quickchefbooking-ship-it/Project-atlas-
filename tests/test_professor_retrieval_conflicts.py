"""Characterization tests for ambiguous/conflicting approved memory retrieval.

Synthetic-only. These tests do not make retrieval resolve conflicts; they ensure
relevant conflicting records remain visible so the reasoning layer can disclose
the conflict instead of silently selecting one.
"""
import sqlite3

from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.tenant_professor_memory import (
    TenantProfessorMemoryRepository,
    initialize_tenant_memory_schema,
)


def _memory_repo():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    initialize_tenant_memory_schema(db)
    principal = RequestPrincipal(
        "https://evaluation.example.test", "fixture", "fixture-tenant", True,
        frozenset({"memory:propose", "memory:approve", "memory:read"}),
    )
    repo = TenantProfessorMemoryRepository(db, principal)
    return db, repo


def _approved(repo, proposal_id, title, content):
    repo.propose(proposal_id, category="project", title=title, content=content)
    repo.decide(proposal_id, decision="approved", rationale="Synthetic conflict fixture.")


def test_conflicting_approved_memories_are_both_retrievable():
    db, repo = _memory_repo()
    try:
        _approved(repo, "browser-a", "Primary browser", "Use Safari first for iPhone testing.")
        _approved(repo, "browser-b", "Primary browser", "Use Chrome first for iPhone testing.")
        results = repo.retrieve("primary browser iPhone testing", limit=5)
        ids = {item["proposal_id"] for item in results}
        assert {"browser-a", "browser-b"}.issubset(ids)
    finally:
        db.close()


def test_retrieval_does_not_claim_resolution_of_conflicting_memories():
    db, repo = _memory_repo()
    try:
        _approved(repo, "voice-a", "Voice activation", "Wake phrase is Hey Atlas.")
        _approved(repo, "voice-b", "Voice activation", "Wake phrase is Atlas.")
        results = repo.retrieve("voice activation wake phrase", limit=5)
        contents = {item["content"] for item in results}
        assert "Wake phrase is Hey Atlas." in contents
        assert "Wake phrase is Atlas." in contents
        # The repository returns evidence only; it has no resolution field.
        assert all("resolution" not in item for item in results)
    finally:
        db.close()


def test_multilingual_query_abstains_without_matching_memory():
    db, repo = _memory_repo()
    try:
        _approved(repo, "memory-en", "Project focus", "Build the reasoning brain before integrations.")
        results = repo.retrieve("¿Cuál es el pronóstico del tiempo mañana?", limit=5)
        assert results == ()
    finally:
        db.close()
