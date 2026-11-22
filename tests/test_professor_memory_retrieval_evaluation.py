"""Offline relevance evaluation for the deterministic memory retrieval baseline.

The corpus is synthetic and test-only. It does not use real user memories,
external services, model inference, or persistent application data.
"""
import sqlite3

import pytest

from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.tenant_professor_memory import (
    TenantProfessorMemoryRepository,
    initialize_tenant_memory_schema,
)


CORPUS = (
    ("atlas-priority", "project", "AtlasOnePro brain priority",
     "Keep central reasoning and memory foundations ahead of peripheral features."),
    ("atlas-platform", "project", "AtlasOnePro platform",
     "Browser first product for iPhone and other devices."),
    ("quickchef", "project", "Quick Chef bookings",
     "Chef registration and customer booking workflow."),
    ("writing-style", "preference", "Concise writing style",
     "Prefer clear concise explanations without unnecessary repetition."),
    ("security", "security", "Enterprise security posture",
     "SOC 2 readiness UK GDPR and careful tenant isolation."),
    ("voice", "interface", "Professor voice interface",
     "Natural conversational speech and wake phrase activation."),
    ("finance", "finance", "Trading account integration",
     "Trading212 portfolio data and investment tracking."),
    ("cooking", "interest", "Food safety",
     "Kitchen labelling allergen control and stock rotation."),
)

CASES = (
    ("What should AtlasOnePro build first: central brain or peripheral features?",
     {"atlas-priority"}),
    ("How should Professor sound when speaking?",
     {"voice"}),
    ("What writing style should answers use?",
     {"writing-style"}),
    ("What controls matter for enterprise tenant data?",
     {"security"}),
    ("Where is the chef booking workflow?",
     {"quickchef"}),
)


def _metrics(ranked_ids, relevant_ids, k=3):
    top_k = ranked_ids[:k]
    hits = sum(item in relevant_ids for item in top_k)
    recall = hits / len(relevant_ids) if relevant_ids else 1.0
    precision = hits / k
    reciprocal_rank = next(
        (1 / rank for rank, item in enumerate(ranked_ids, start=1)
         if item in relevant_ids),
        0.0,
    )
    return recall, precision, reciprocal_rank


@pytest.fixture
def evaluation_repository():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    initialize_tenant_memory_schema(db)
    principal = RequestPrincipal(
        "https://atlas.example.test",
        "synthetic-evaluation-owner",
        "synthetic-evaluation-tenant",
        True,
        frozenset({"memory:propose", "memory:approve", "memory:read"}),
    )
    repository = TenantProfessorMemoryRepository(db, principal)
    for proposal_id, category, title, body in CORPUS:
        repository.propose(
            proposal_id, category=category, title=title, content=body
        )
        repository.decide(proposal_id, decision="approved",
                          rationale="Synthetic offline evaluation fixture.")
    yield repository
    db.close()


def test_synthetic_memory_retrieval_corpus_meets_baseline_metrics(
    evaluation_repository,
):
    per_case = []
    for query, relevant_ids in CASES:
        results = evaluation_repository.retrieve(query, limit=8)
        ranked_ids = [item["proposal_id"] for item in results]
        recall, precision, reciprocal_rank = _metrics(
            ranked_ids, relevant_ids, k=3
        )
        per_case.append((recall, precision, reciprocal_rank))

    mean_recall = sum(row[0] for row in per_case) / len(per_case)
    mean_precision = sum(row[1] for row in per_case) / len(per_case)
    mean_reciprocal_rank = sum(row[2] for row in per_case) / len(per_case)

    # This is a transparent regression floor for a small lexical smoke corpus,
    # not evidence of semantic understanding or production relevance.
    assert mean_recall >= 0.80
    assert mean_precision >= 0.20
    assert mean_reciprocal_rank >= 0.80


def test_retrieval_metrics_handle_missing_relevant_items():
    recall, precision, reciprocal_rank = _metrics(
        ["unrelated-a", "unrelated-b", "unrelated-c"],
        {"expected-memory"},
        k=3,
    )
    assert recall == 0.0
    assert precision == 0.0
    assert reciprocal_rank == 0.0


def test_retrieval_metrics_reward_first_position():
    recall, precision, reciprocal_rank = _metrics(
        ["expected-memory", "unrelated-a", "unrelated-b"],
        {"expected-memory"},
        k=3,
    )
    assert recall == 1.0
    assert precision == pytest.approx(1 / 3)
    assert reciprocal_rank == 1.0
