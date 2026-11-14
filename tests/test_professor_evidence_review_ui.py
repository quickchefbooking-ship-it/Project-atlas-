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
