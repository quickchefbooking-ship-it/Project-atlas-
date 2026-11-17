from pathlib import Path


def test_professor_chat_page_uses_verified_bearer_api_without_persisting_token():
    page = Path(__file__).resolve().parents[1] / "static" / "professor_chat.html"
    html = page.read_text(encoding="utf-8")

    assert 'token?{Authorization:"Bearer "+token}:{}' in html
    assert 'credentials:"same-origin"' in html
    assert 'headers["X-Atlas-CSRF"]=csrf' in html
    assert 'window.location.assign("/identity/login")' in html
    assert 'request("/identity/logout",{method:"POST"})' in html
    assert 'const CSRF_COOKIE="__Host-atlas_csrf"' in html
    assert 'request("/identity/me")' in html
    assert 'fetch("/identity/login-readiness")' in html
    assert "Use organisation sign-in when hosted OIDC is configured." in html
    assert 'id="signIn"' in html
    assert '"conversations:read"' in html
    assert '"conversations:write"' in html
    assert '"/professor/conversation"' in html
    assert '"/professor/conversations"' in html
    assert '"/trace"' in html
    assert "localStorage" not in html
    assert "sessionStorage" not in html
    assert 'token="";$("token").value=""' in html
    assert "X-API-Key" not in html


def test_professor_chat_page_is_served_by_application_route():
    app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text(
        encoding="utf-8"
    )
    assert '@app.get("/professor/chat", include_in_schema=False)' in app_source
    assert ' / "professor_chat.html"' in app_source
