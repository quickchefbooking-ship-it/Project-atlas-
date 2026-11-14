from fastapi.testclient import TestClient

import app as app_module


def test_evidence_review_page_is_served_without_exposing_review_data():
    with TestClient(app_module.app) as client:
        response = client.get("/professor/evidence-review")
    assert response.status_code == 200
    assert "Evidence review" in response.text
    assert "OIDC bearer access token" in response.text
    assert '"Authorization":"Bearer "' in response.text
    assert "localStorage" not in response.text
    assert "sessionStorage" not in response.text


def test_professor_report_page_is_read_only_and_uses_tenant_plan_api():
    with TestClient(app_module.app) as client:
        response = client.get("/professor/report")
    assert response.status_code == 200
    assert "Research report" in response.text
    assert "OIDC bearer access token" in response.text
    assert "/professor/tenant/plans/" in response.text
    assert "professor_evidence_report" in response.text
    assert "localStorage" not in response.text
    assert "sessionStorage" not in response.text
    assert "execute-next" not in response.text
