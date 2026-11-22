import base64
import json
from urllib.parse import parse_qs, quote_plus

import httpx
import pytest

from atlas_engine.oidc_browser_login import OIDCBrowserLoginError
from atlas_engine.oidc_http_token_exchange import HTTPSOIDCAuthorizationCodeExchanger


ENDPOINT = "https://identity.example.test/oauth/token"
REDIRECT_URI = "https://atlas.example.test/identity/callback"
CLIENT_ID = "atlas-browser-client"
CODE = "provider-one-time-code"
VERIFIER = "v" * 43
TOKEN_PAYLOAD = {
    "id_token": "header.payload.signature",
    "access_token": "provider-access-token",
    "token_type": "Bearer",
}


def _exchanger(handler, **overrides):
    values = {
        "token_endpoint": ENDPOINT,
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "transport": httpx.MockTransport(handler),
    }
    values.update(overrides)
    return HTTPSOIDCAuthorizationCodeExchanger(**values)


def _json_response(payload, *, status=200, headers=None):
    response_headers = {"content-type": "application/json"}
    if headers:
        response_headers.update(headers)
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return httpx.Response(status, headers=response_headers, content=body)


def test_public_client_posts_code_verifier_and_fixed_redirect_uri():
    captured = []

    def handler(request):
        captured.append(request)
        return _json_response(TOKEN_PAYLOAD)

    result = _exchanger(handler).exchange(CODE, VERIFIER, REDIRECT_URI)

    request = captured[0]
    form = parse_qs(request.content.decode())
    assert request.method == "POST"
    assert str(request.url) == ENDPOINT
    assert form == {
        "grant_type": ["authorization_code"],
        "code": [CODE],
        "redirect_uri": [REDIRECT_URI],
        "code_verifier": [VERIFIER],
        "client_id": [CLIENT_ID],
    }
    assert request.headers["accept"] == "application/json"
    assert "authorization" not in request.headers
    assert result.id_token == TOKEN_PAYLOAD["id_token"]
    assert result.access_token == TOKEN_PAYLOAD["access_token"]
    assert result.token_type == "Bearer"


def test_confidential_client_uses_basic_auth_and_never_puts_secret_in_body():
    secret = "deployment-secret with symbols:!?"
    captured = []

    def handler(request):
        captured.append(request)
        return _json_response(TOKEN_PAYLOAD)

    exchanger = _exchanger(
        handler,
        client_secret=secret,
    )
    exchanger.exchange(CODE, VERIFIER, REDIRECT_URI)

    request = captured[0]
    encoded = request.headers["authorization"].removeprefix("Basic ")
    decoded = base64.b64decode(encoded).decode("ascii")
    assert decoded == f"{quote_plus(CLIENT_ID, safe='')}:{quote_plus(secret, safe='')}"
    form = parse_qs(request.content.decode())
    assert "client_id" not in form
    assert secret not in request.content.decode()
    assert secret not in repr(exchanger)


def test_redirect_response_is_not_followed():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://attacker.example.test/token"})

    with pytest.raises(OIDCBrowserLoginError, match="exchange failed"):
        _exchanger(handler).exchange(CODE, VERIFIER, REDIRECT_URI)

    assert len(calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, content=b"private provider detail and secret"),
        httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html>"),
        httpx.Response(200, headers={"content-type": "application/json"}, content=b"not-json"),
        httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=b'{"id_token":"first","id_token":"second","access_token":"a","token_type":"Bearer"}',
        ),
        _json_response({"id_token": "id", "access_token": "access", "token_type": "MAC"}),
        _json_response({"access_token": "access", "token_type": "Bearer"}),
        _json_response({"id_token": "id", "access_token": "access", "token_type": 7}),
    ],
)
def test_untrusted_or_malformed_provider_responses_are_rejected_without_leaking_details(response):
    def handler(_request):
        return response

    with pytest.raises(OIDCBrowserLoginError) as error:
        _exchanger(handler).exchange(CODE, VERIFIER, REDIRECT_URI)

    assert "private provider detail" not in str(error.value)
    assert "secret" not in str(error.value)
    assert "token" not in repr(error.value).lower() or "response" in str(error.value).lower()


def test_content_length_above_limit_is_rejected_before_body_is_read():
    body = json.dumps(
        {
            "id_token": "i" * 100,
            "access_token": "a" * 100,
            "token_type": "Bearer",
        }
    ).encode()

    def handler(_request):
        return httpx.Response(
            200,
            headers={
                "content-type": "application/json",
                "content-length": str(len(body)),
            },
            content=body,
        )

    with pytest.raises(OIDCBrowserLoginError, match="size limit"):
        _exchanger(handler, max_response_bytes=128).exchange(CODE, VERIFIER, REDIRECT_URI)


def test_streamed_body_without_content_length_is_still_bounded():
    class Chunks(httpx.SyncByteStream):
        def __iter__(self):
            yield b"x" * 80
            yield b"y" * 80

    def handler(_request):
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=Chunks(),
        )

    with pytest.raises(OIDCBrowserLoginError, match="size limit"):
        _exchanger(handler, max_response_bytes=128).exchange(CODE, VERIFIER, REDIRECT_URI)


@pytest.mark.parametrize(
    "code,verifier,redirect_uri",
    [
        ("", VERIFIER, REDIRECT_URI),
        ("bad\ncode", VERIFIER, REDIRECT_URI),
        ("c" * 4097, VERIFIER, REDIRECT_URI),
        (CODE, "short", REDIRECT_URI),
        (CODE, "x" * 129, REDIRECT_URI),
        (CODE, "x" * 42 + "!", REDIRECT_URI),
        (CODE, VERIFIER, "https://attacker.example.test/identity/callback"),
    ],
)
def test_invalid_exchange_inputs_are_rejected_before_network_request(code, verifier, redirect_uri):
    calls = []

    def handler(request):
        calls.append(request)
        return _json_response(TOKEN_PAYLOAD)

    with pytest.raises(OIDCBrowserLoginError):
        _exchanger(handler).exchange(code, verifier, redirect_uri)

    assert calls == []


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://identity.example.test/oauth/token",
        "https://user:pass@identity.example.test/oauth/token",
        "https://identity.example.test/oauth/token?next=https://attacker.example.test",
        "https://identity.example.test/oauth/token#fragment",
        "https://identity.example.test/oauth/token#",
        "https://identity.example.test:0/oauth/token",
        "https://identity.example.test/oauth/token with-space",
    ],
)
def test_unsafe_token_endpoints_are_rejected(endpoint):
    with pytest.raises(ValueError):
        HTTPSOIDCAuthorizationCodeExchanger(
            endpoint,
            CLIENT_ID,
            REDIRECT_URI,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"client_id": ""},
        {"client_id": "bad\nclient"},
        {"client_secret": ""},
        {"timeout_seconds": 0},
        {"timeout_seconds": 31},
        {"timeout_seconds": float("nan")},
        {"max_response_bytes": 127},
        {"max_response_bytes": 65537},
    ],
)
def test_invalid_deployment_configuration_is_rejected(kwargs):
    values = {
        "token_endpoint": ENDPOINT,
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
    }
    values.update(kwargs)
    with pytest.raises((TypeError, ValueError)):
        HTTPSOIDCAuthorizationCodeExchanger(**values)


def test_transport_errors_are_sanitized():
    def handler(_request):
        raise httpx.ConnectError("private host, credential and network details")

    with pytest.raises(OIDCBrowserLoginError) as error:
        _exchanger(handler).exchange(CODE, VERIFIER, REDIRECT_URI)

    assert str(error.value) == "OIDC authorization-code exchange failed."
    assert "private host" not in str(error.value)
    assert "credential" not in str(error.value)
