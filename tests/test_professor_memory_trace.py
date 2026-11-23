"""Privacy and determinism tests for opt-in memory retrieval traces."""
import sqlite3

from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.tenant_professor_memory import (
    TenantProfessorMemoryRepository,
    initialize_tenant_memory_schema,
)
from atlas_engine.tenant_professor_memory_trace import (
    TRACE_VERSION,
    explain_memory_retrieval,
)


def _repo():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    initialize_tenant_memory_schema(db)
    principal = RequestPrincipal(
        "https://trace.example.test", "fixture", "trace-tenant", True,
        frozenset({"memory:propose", "memory:approve", "memory:read"}),
    )
    repo = TenantProfessorMemoryRepository(db, principal)
    repo.propose("security", category="security", title="Enterprise safeguards",
                  content="SOC 2 readiness, GDPR, tenant isolation and access control.")
    repo.decide("security", decision="approved", rationale="Synthetic fixture.")
    repo.propose("pending", category="security", title="Pending secret",
                  content="Should not be exposed.")
    return db, repo


def test_trace_is_bounded_and_does_not_expose_query_or_memory_content():
    db, repo = _repo()
    try:
        trace = explain_memory_retrieval(repo, "What safeguards protect enterprise data?", limit=3)
        assert trace["trace_version"] == TRACE_VERSION
        assert trace["candidate_count"] == 1
        candidate = trace["candidates"][0]
        assert candidate["proposal_id"] == "security"
        assert candidate["rank"] == 1
        assert candidate["matched_fields"]
        assert "content" not in candidate
        assert "query" not in trace
        assert "Pending secret" not in repr(trace)
        assert "Should not be exposed" not in repr(trace)
    finally:
        db.close()


def test_trace_is_deterministic_for_same_query_and_repository_state():
    db, repo = _repo()
    try:
        first = explain_memory_retrieval(repo, "enterprise safeguards data")
        second = explain_memory_retrieval(repo, "enterprise safeguards data")
        assert first == second
    finally:
        db.close()


def test_trace_abstains_for_unrelated_query_and_validates_limit():
    db, repo = _repo()
    try:
        assert explain_memory_retrieval(repo, "weather tomorrow")["candidates"] == []
        for bad_limit in (0, 21, True, "5"):
            try:
                explain_memory_retrieval(repo, "security", limit=bad_limit)
            except ValueError:
                pass
            else:
                raise AssertionError(f"Expected limit validation for {bad_limit!r}")
    finally:
        db.close()
