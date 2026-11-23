"""Expanded labelled retrieval checks: paraphrases, distractors and abstention.

Synthetic only; never reads production or personal memory.
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
    ("distractor", "project", "Video production arm", "Video editing, captions and media output."),
)

CASES = (
    ("paraphrase", "What is the main thing we should focus on before adding features?", {"brain"}),
    ("paraphrase", "What device and browser should the product work on first?", {"platform"}),
    ("paraphrase", "How do we onboard cooks and arrange customer reservations?", {"quickchef"}),
    ("paraphrase", "How should replies be written?", {"style"}),
    ("paraphrase", "What safeguards should protect company and customer data?", {"security"}),
    ("paraphrase", "What spoken interface and activation phrase are planned?", {"voice"}),
    ("paraphrase", "Which brokerage portfolio integration was discussed?", {"finance"}),
    ("distractor", "What is the video editing and captioning specialist arm?", {"distractor"}),
    ("no_answer", "What is the weather forecast and rainfall tomorrow?", set()),
)


def _repo():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    initialize_tenant_memory_schema(db)
    principal = RequestPrincipal(
        "https://evaluation.example.test", "fixture", "fixture-tenant", True,
        frozenset({"memory:propose", "memory:approve", "memory:read"}),
    )
    repo = TenantProfessorMemoryRepository(db, principal)
    for pid, category, title, body in CORPUS:
        repo.propose(pid, category=category, title=title, content=body)
        repo.decide(pid, decision="approved", rationale="Synthetic labelled benchmark.")
    return db, repo


def test_expanded_labelled_benchmark_reports_per_query_retrieval():
    db, repo = _repo()
    try:
        failures = []
        answerable = [(category, query, relevant) for category, query, relevant in CASES if relevant]
        reciprocal_ranks = []
        hits_at_3 = 0
        precision_at_3_total = 0.0
        for category, query, relevant in CASES:
            ids = [item["proposal_id"] for item in repo.retrieve(query, limit=5)]
            if relevant:
                rank = next((index for index, pid in enumerate(ids, start=1) if pid in relevant), None)
                reciprocal_ranks.append(1.0 / rank if rank is not None else 0.0)
                top3 = ids[:3]
                hits_at_3 += int(bool(set(top3) & relevant))
                precision_at_3_total += len(set(top3) & relevant) / max(1, len(top3))
                if not set(top3) & relevant:
                    failures.append((category, query, sorted(relevant), ids))
            elif ids:
                failures.append((category, query, sorted(relevant), ids))

        recall_at_3 = hits_at_3 / len(answerable)
        mean_reciprocal_rank = sum(reciprocal_ranks) / len(reciprocal_ranks)
        precision_at_3 = precision_at_3_total / len(answerable)
        # Transparent diagnostic gate; these lexical metrics do not establish
        # semantic understanding. Keep per-query failures visible.
        assert recall_at_3 >= 0.875, (
            f"Recall@3={recall_at_3:.3f}; MRR={mean_reciprocal_rank:.3f}; "
            f"Precision@3={precision_at_3:.3f}; failures={failures}"
        )
        no_answer_ids = [item["proposal_id"] for item in repo.retrieve(CASES[-1][1], limit=5)]
        assert no_answer_ids == [], f"No-answer query retrieved unrelated memories: {no_answer_ids}"
    finally:
        db.close()


def test_superseded_memory_is_removed_from_candidate_set():
    db, repo = _repo()
    try:
        repo.propose("old", category="preference", title="Answer length",
                     content="Always give very long answers.")
        repo.decide("old", decision="approved")
        repo.propose("new", category="preference", title="Answer length",
                     content="Keep answers concise.")
        repo.decide("new", decision="approved")
        repo.confirm_supersession("old", "new", confirmed=True, rationale="Owner corrected preference.")
        results = repo.retrieve("answer length concise", limit=5)
        ids = [item["proposal_id"] for item in results]
        assert "new" in ids
        assert "old" not in ids
    finally:
        db.close()
