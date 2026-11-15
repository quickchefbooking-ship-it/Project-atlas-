from atlas_engine.capability_runtime import build_default_capability_runtime


def test_professor_report_capability_consumes_completed_bundle_and_evaluation():
    runtime = build_default_capability_runtime()
    bundle = {
        "schema_version": 1,
        "sources": [{
            "source_id": "source-1", "title": "Study", "uri": "https://doi.org/10.1000/a",
            "doi": "10.1000/a", "publisher": "Press", "retrieved_at": "2026-11-14",
        }],
        "claims": [],
        "duplicate_records": [],
        "summary": {},
        "limitations": ["No independent verification."],
    }
    evaluation = {
        "schema_version": 1,
        "evaluations": [{
            "claim_id": "c1", "text": "A supplied claim",
            "status": "supported_by_supplied_annotations",
            "supporting_source_ids": ["source-1"], "challenging_source_ids": [],
            "mentioning_source_ids": [], "confidence": "not_scored",
            "interpretation": "Supplied annotation only.",
        }],
        "summary": {"confidence": "not_scored"},
        "limitations": ["No confidence scoring."],
    }
    payload = runtime.input_for_objective(
        "research.professor.report", "1.0.0", "Prepare a report",
        dependency_outputs={"bundle-step": bundle, "evaluation-step": evaluation},
    )
    result = runtime.execute("research.professor.report", "1.0.0", payload)
    assert result["report_type"] == "professor_evidence_report"
    assert result["findings"][0]["source_references"] == ["source-1"]
    assert result["sources"][0]["title"] == "Study"
    assert result["executive_summary"]["confidence"] == "not_scored"


def test_professor_report_capability_requires_both_completed_dependencies():
    runtime = build_default_capability_runtime()
    try:
        runtime.input_for_objective(
            "research.professor.report", "1.0.0", "Prepare report",
            dependency_outputs={"evaluation-step": {"schema_version": 1, "evaluations": []}},
        )
    except Exception as exc:
        assert "not both available" in str(exc)
    else:
        raise AssertionError("Reporting must require both a bundle and an evaluation.")
