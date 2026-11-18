from pathlib import Path


def test_professor_chat_page_uses_verified_bearer_api_without_persisting_token():
    page = Path(__file__).resolve().parents[1] / "static" / "professor_chat.html"
    html = page.read_text(encoding="utf-8")

    assert 'Authorization:"Bearer "+token' in html
    assert 'request("/identity/me")' in html
    assert 'fetch("/identity/login-readiness")' in html
    assert "Hosted organisation sign-in is the target." in html
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

def test_professor_chat_reports_actual_provider_and_does_not_fake_failed_turns():
    page = Path(__file__).resolve().parents[1] / "static" / "professor_chat.html"
    html = page.read_text(encoding="utf-8")
    send_function = html.split("async function send()", 1)[1].split(
        '  $("connect")', 1
    )[0]

    assert 'id="responseMeta"' in html
    assert 'd.provider' in send_function
    assert 'd.model' in send_function
    assert 'd.reasoning_status' in send_function
    assert 'd.execution_enabled===false' in send_function
    assert send_function.index('request("/professor/conversation"') < send_function.index(
        'bubble("user",value)'
    )
    assert 'bubble("assistant","I couldn\\'t complete that response:' not in send_function
    assert "The server may have completed the turn" in send_function
    assert 'if(input.value.trim()===value)input.value=""' in send_function
