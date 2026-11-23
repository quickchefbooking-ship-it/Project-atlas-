"""Executable baseline metrics for THE PROFESSOR memory retrieval.

Synthetic-only. Prints metrics for CI logs so a later candidate can be compared
against the same corpus and queries.
"""
import sqlite3

from atlas_engine.identity_policy import RequestPrincipal
from atlas_engine.tenant_professor_memory import (
    TenantProfessorMemoryRepository,
    initialize_tenant_memory_schema,
)

CORPUS = (
    ("brain", "project", "AtlasOnePro brain priority", "Core reasoning memory and learning foundations before peripheral features."),
    ("platform", "project", "AtlasOnePro platform", "Browser first and iPhone Safari support."),
    ("quickchef", "project", "Quick Chef bookings", "Chef registration, profiles and customer bookings."),
    ("style", "preference", "Concise writing style", "Clear concise answers without unnecessary repetition."),
    ("security", "security", "Enterprise security posture", "SOC 2 readiness, UK GDPR and tenant isolation."),
    ("voice", "interface", "Professor voice interface", "Natural speech and wake phrase activation."),
    ("finance", "finance", "Trading account integration", "Trading212 portfolio tracking."),
    ("food", "interest", "Food safety", "Kitchen labelling, allergens and stock rotation."),
    ("video", "project", "Video production arm", "Video editing, captions and media output."),
)

QUERIES = (
    ("What is the main thing we should focus on before adding features?", {"brain"}),
    ("What device and browser should the product work on first?", {"platform"}),
    ("How do we onboard cooks and arrange customer reservations?", {"quickchef"}),
    ("How should replies be written?", {"style"}),
    ("What safeguards should protect company and customer data?", {"security"}),
    ("What spoken interface and activation phrase are planned?", {"voice"}),
    ("Which brokerage portfolio integration was discussed?", {"finance"}),
    ("What editing and captioning tools belong in the video arm?", {"video"}),
    ("What kitchen food safety topics were discussed?", {"food"}),
)
NO_ANSWER = (
    "What is the weather forecast and rainfall tomorrow?",
    "How many planets are visible tonight?",
)


def _repo():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    initialize_tenant_memory_schema(db)
    principal = RequestPrincipal(
        "https://matched-benchmark.example.test", "fixture", "fixture-tenant", True,
        frozenset({"memory:propose", "memory:approve", "memory:read"}),
    )
    repo = TenantProfessorMemoryRepository(db, principal)
    for pid, category, title, body in CORPUS:
        repo.propose(pid, category=category, title=title, content=body)
        repo.decide(pid, decision="approved", rationale="Synthetic benchmark fixture.")
    return db, repo


def test_retrieval_baseline_reports_matched_metrics_and_abstention():
    db, repo = _repo()
    try:
        reciprocal_ranks = []
        hits = {1: 0, 3: 0, 5: 0}
        precisions = {3: [], 5: []}
        per_query = []
        for query, relevant in QUERIES:
            ids = [item["proposal_id"] for item in repo.retrieve(query, limit=5)]
            rank = next((i for i, pid in enumerate(ids, start=1) if pid in relevant), None)
            reciprocal_ranks.append(1.0 / rank if rank else 0.0)
            for k in hits:
                hits[k] += int(bool(set(ids[:k]) & relevant))
            for k in precisions:
                precisions[k].append(len(set(ids[:k]) & relevant) / k)
            per_query.append((query, sorted(relevant), ids, rank))

        recall = {k: hits[k] / len(QUERIES) for k in hits}
        precision = {k: sum(values) / len(values) for k, values in precisions.items()}
        mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)
        false_positives = {
            query: [item["proposal_id"] for item in repo.retrieve(query, limit=5)]
            for query in NO_ANSWER
        }

        print("MATCHED RETRIEVAL BASELINE")
        print(f"Recall@1={recall[1]:.4f} Recall@3={recall[3]:.4f} Recall@5={recall[5]:.4f}")
        print(f"Precision@3={precision[3]:.4f} Precision@5={precision[5]:.4f} MRR={mrr:.4f}")
        print(f"No-answer false-positive queries={sum(bool(v) for v in false_positives.values())}/{len(NO_ANSWER)}")
        print(f"Per-query={per_query}")
        print(f"No-answer={false_positives}")

        assert recall[3] >= 0.875, f"Recall@3 gate failed: {per_query}"
        assert all(not results for results in false_positives.values()), false_positives
    finally:
        db.close()
