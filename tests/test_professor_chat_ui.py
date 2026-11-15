from pathlib import Path


def test_professor_chat_page_uses_verified_bearer_api_without_persisting_token():
    page = Path(__file__).resolve().parents[1] / "static" / "professor_chat.html"
    html = page.read_text(encoding="utf-8")

    assert 'Authorization:"Bearer "+token' in html
    assert 'request("/identity/me")' in html
    assert '"conversations:read"' in html
    assert '"conversations:write"' in html
    assert '"/professor/conversation"' in html
    assert '"/professor/conversations"' in html
    assert '"/trace"' in html
    assert "localStorage" not in html
    assert "sessionStorage" not in html
    assert "X-API-Key" not in html


def test_professor_chat_page_is_served_by_application_route():
    app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text(
        encoding="utf-8"
    )
    assert '@app.get("/professor/chat", include_in_schema=False)' in app_source
    assert ' / "professor_chat.html"' in app_source
