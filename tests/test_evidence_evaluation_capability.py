from atlas_engine.capability_runtime import build_default_capability_runtime


def test_professor_evaluation_capability_consumes_completed_evidence_bundle():
    runtime = build_default_capability_runtime()
    bundle = {
        "schema_version": 1,
        "sources": [{
            "source_id": "source-1",
            "title": "Example study",
            "uri": "https://doi.org/10.1000/example",
            "doi": "10.1000/example",
            "publisher": "Example Press",
            "retrieved_at": "2026-11-14T12:00:00Z",
        }],
        "claims": [{
            "claim_id": "c1",
            "text": "A supplied claim",
            "annotations": [{"source_id": "source-1", "relation": "supports"}],
        }],
        "duplicate_records": [],
        "summary": {"confidence": "not_scored"},
        "limitations": [],
    }
    payload = runtime.input_for_objective(
        "research.evidence.evaluate",
        "1.0.0",
        "Evaluate the evidence",
        dependency_outputs={"evidence-step": bundle},
    )
    result = runtime.execute("research.evidence.evaluate", "1.0.0", payload)
    assert result["evaluations"][0]["status"] == "supported_by_supplied_annotations"
    assert result["evaluations"][0]["supporting_source_ids"] == ["source-1"]
    assert result["evaluations"][0]["confidence"] == "not_scored"


def test_professor_evaluation_capability_refuses_missing_evidence_dependency():
    runtime = build_default_capability_runtime()
    try:
        runtime.input_for_objective(
            "research.evidence.evaluate", "1.0.0", "Evaluate",
            dependency_outputs={"math-step": {"value": 4}},
        )
    except Exception as exc:
        assert "No completed evidence bundle" in str(exc)
    else:
        raise AssertionError("Evaluation must require an evidence bundle dependency.")
