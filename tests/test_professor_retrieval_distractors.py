"""Focused retrieval distractor checks for THE PROFESSOR memory search.

Synthetic fixtures only. These characterize the current lexical/synonym system
and provide a small regression gate before broader matched benchmarks.
"""
import sqlite3

from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.tenant_professor_memory import (
    TenantProfessorMemoryRepository,
    initialize_tenant_memory_schema,
)

MEMORIES = (
    ("brain", "project", "AtlasOnePro brain priority",
     "Core reasoning memory and learning foundations before peripheral features."),
    ("quickchef", "project", "Quick Chef bookings",
     "Chef registration, profiles and customer bookings."),
    ("security", "security", "Enterprise security posture",
     "SOC 2 readiness, UK GDPR and tenant isolation."),
    ("voice", "interface", "Professor voice interface",
     "Natural speech and wake phrase activation."),
    ("finance", "finance", "Trading account integration",
     "Trading212 portfolio tracking."),
    ("video", "project", "Video production arm",
     "Video editing, captions and media output."),
)

CASES = (
    ("What should we prioritize before peripheral features?", {"brain"}),
    ("How do cooks register and customers make reservations?", {"quickchef"}),
    ("What protects enterprise and customer information?", {"security"}),
    ("What voice activation phrase and speech interface?", {"voice"}),
    ("Which brokerage portfolio did we discuss?", {"finance"}),
    ("What editing and captioning tools belong in the video arm?", {"video"}),
    ("What is the weather forecast tomorrow?", set()),
    ("How many planets are visible tonight?", set()),
)


def _repository():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    initialize_tenant_memory_schema(db)
    principal = RequestPrincipal(
        "https://retrieval-eval.example.test", "fixture", "fixture-tenant", True,
        frozenset({"memory:propose", "memory:approve", "memory:read"}),
    )
    repo = TenantProfessorMemoryRepository(db, principal)
    for proposal_id, category, title, body in MEMORIES:
        repo.propose(proposal_id, category=category, title=title, content=body)
        repo.decide(proposal_id, decision="approved", rationale="Synthetic evaluation fixture.")
    return db, repo


def test_distractor_suite_recall_at_three_and_no_answer_abstention():
    db, repo = _repository()
    try:
        answerable = [case for case in CASES if case[1]]
        hits = 0
        failures = []
        for query, expected in CASES:
            results = repo.retrieve(query, limit=5)
            ids = [item["proposal_id"] for item in results]
            if expected:
                if set(ids[:3]) & expected:
                    hits += 1
                else:
                    failures.append((query, sorted(expected), ids))
            elif ids:
                failures.append((query, [], ids))

        recall_at_3 = hits / len(answerable)
        assert recall_at_3 == 1.0, (
            f"Focused Recall@3={recall_at_3:.3f}; failures={failures}"
        )
        assert not failures, f"Unexpected retrieval or abstention failures: {failures}"
    finally:
        db.close()
