import json
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from atlas_engine import storage
from atlas_engine.learning_memory import LearningMemory
from atlas_market import build_synthetic_market_snapshot
from atlas_market.professor_evidence import (ProfessorEvidenceError,
    get_professor_market_guidance, record_market_observation, record_watchlist_evidence)

def _isolated_db(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "professor-market.db"))
    storage.init_db()
    now = storage.now_isoformat()
    storage.save_task({"id":"market-evidence-task","title":"Market evidence",
      "description":"Record synthetic evidence","success_criteria_json":"[]",
      "status":"passed","attempts":1,"score":1.0,"result_json":"{}",
      "created_at":now,"updated_at":now})

def test_observation_is_unvalidated_and_not_guidance(monkeypatch,tmp_path):
    _isolated_db(monkeypatch,tmp_path)
    result=record_market_observation(task_id="market-evidence-task",
      summary="Synthetic fixture passed validation",outcome="verified",source="unit-test",
      evidence={"price":Decimal("12.3400"),"mode":"synthetic"},
      observed_at=datetime(2026,11,18,tzinfo=timezone.utc))
    assert result["validated"] is False and result["guidance_eligible"] is False
    lesson=storage.list_lessons(limit=10)[0]
    evidence=json.loads(lesson["evidence_json"])
    assert evidence["evidence_sha256"]==result["evidence_sha256"]
    assert evidence["evidence"]["price"]=="12.3400"
    assert evidence["observed_at"].endswith("+00:00")
    assert LearningMemory.get_relevant_lessons("atlas market synthetic",limit=5)==[]

def test_failed_partial_uncertain_outcomes_remain_distinct(monkeypatch,tmp_path):
    _isolated_db(monkeypatch,tmp_path)
    for outcome in ("failed","partial","uncertain"):
        record_market_observation(task_id="market-evidence-task",
          summary=f"Market task {outcome}",outcome=outcome,source="unit-test",evidence={})
    records=storage.list_lessons(limit=10)
    assert {r["lesson_type"] for r in records}=={
      "market_failed","market_partial","market_uncertain"}
    assert all(r["validated"]==0 for r in records)

def test_synthetic_watchlist_records_provenance_and_claim_scope(monkeypatch,tmp_path):
    _isolated_db(monkeypatch,tmp_path)
    result=record_watchlist_evidence(task_id="market-evidence-task",
      items=build_synthetic_market_snapshot())
    assert result["domain"]=="atlas_market_intelligence"
    evidence=json.loads(storage.list_lessons(limit=1)[0]["evidence_json"])["evidence"]
    assert evidence["mode"]=="synthetic"
    assert "not real market observations" in evidence["claim_scope"]
    assert all(i["data_status"]=="synthetic" for i in evidence["items"])

def test_guidance_only_uses_owner_validated_market_lessons(monkeypatch,tmp_path):
    _isolated_db(monkeypatch,tmp_path)
    record_market_observation(task_id="market-evidence-task",
      summary="Unreviewed synthetic lesson must not guide Professor",
      outcome="verified",source="unit-test",evidence={"mode":"synthetic"})
    assert get_professor_market_guidance("synthetic fixture")==[]
    storage.save_lesson({"id":"reviewed-market-lesson","task_id":"market-evidence-task",
      "lesson_type":"market_verified","summary":"Owner reviewed synthetic validation procedure",
      "source":"human-review","evidence_json":json.dumps({"domain":"atlas_market_intelligence"}),
      "validated":True,"created_at":storage.now_isoformat()})
    guidance=get_professor_market_guidance("synthetic fixture")
    assert guidance and guidance[0]["lesson_id"]=="reviewed-market-lesson"
    assert guidance[0]["trust"]=="owner_validated"
    assert guidance[0]["mode"]=="advisory_only" and guidance[0]["executable"] is False

@pytest.mark.parametrize("outcome",["success","live","execute",""])
def test_invalid_outcome_rejected(monkeypatch,tmp_path,outcome):
    _isolated_db(monkeypatch,tmp_path)
    with pytest.raises(ProfessorEvidenceError,match="outcome|Unsupported"):
        record_market_observation(task_id="market-evidence-task",summary="Reject invalid",
          outcome=outcome,source="test",evidence={})

def test_naive_timestamp_rejected(monkeypatch,tmp_path):
    _isolated_db(monkeypatch,tmp_path)
    with pytest.raises(ProfessorEvidenceError,match="timezone-aware"):
        record_market_observation(task_id="market-evidence-task",summary="Reject naive",
          outcome="uncertain",source="test",evidence={},observed_at=datetime(2026,11,18))

def test_unsupported_and_oversized_evidence_rejected(monkeypatch,tmp_path):
    _isolated_db(monkeypatch,tmp_path)
    with pytest.raises(ProfessorEvidenceError,match="unsupported"):
        record_market_observation(task_id="market-evidence-task",summary="Reject",
          outcome="failed",source="test",evidence={"bad":object()})
    with pytest.raises(ProfessorEvidenceError,match="bounded"):
        record_market_observation(task_id="market-evidence-task",summary="Reject large",
          outcome="partial",source="test",evidence={"large":"x"*13000})
