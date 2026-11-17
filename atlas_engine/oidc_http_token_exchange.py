"""Pinned HTTPS OAuth token exchange for Atlas OIDC browser login.

The adapter is provider-neutral. Its token endpoint, client ID and exact
redirect URI are supplied by trusted deployment composition. It never follows
redirects, discovers endpoints, trusts environment proxy settings, or exposes
provider response details to callers.
"""
from __future__ import annotations

import base64
import json
import math
import re
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urlsplit

import httpx

from .oidc_browser_login import OIDCBrowserLoginError, OIDCTokenResponse


_MAX_TOKEN_LENGTH = 8192
_VISIBLE_ASCII = re.compile(r"^[\x21-\x7e]+$")
_PKCE_VERIFIER = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")


def _validate_https_endpoint(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 2048
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
        or "\\" in value
        or "?" in value
        or "#" in value
    ):
        raise ValueError(f"A fixed HTTPS {label} URL is required.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError(f"A fixed HTTPS {label} URL is required.") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port == 0
    ):
        raise ValueError(f"A fixed HTTPS {label} URL is required.")
    return value


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key.")
        result[key] = value
    return result


def _valid_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= _MAX_TOKEN_LENGTH
        and _VISIBLE_ASCII.fullmatch(value) is not None
    )


@dataclass(frozen=True)
class HTTPSOIDCAuthorizationCodeExchanger:
    """Exchange one code at one deployment-pinned HTTPS token endpoint.

    Public clients send the registered client_id in the form body and rely on
    PKCE. When a confidential-client secret is supplied, the adapter uses
    OAuth client_secret_basic and omits client_id from the form body. The
    secret is expected to come directly from deployment secret management.
    """

    token_endpoint: str
    client_id: str
    redirect_uri: str
    client_secret: str | None = field(default=None, repr=False, compare=False)
    timeout_seconds: float = 5.0
    max_response_bytes: int = 16384
    transport: httpx.BaseTransport | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        endpoint = _validate_https_endpoint(self.token_endpoint, "OIDC token endpoint")
        redirect_uri = _validate_https_endpoint(self.redirect_uri, "OIDC redirect")
        if (
            not isinstance(self.client_id, str)
            or not 1 <= len(self.client_id) <= 256
            or _VISIBLE_ASCII.fullmatch(self.client_id) is None
        ):
            raise ValueError("A registered OIDC client ID is required.")
        if self.client_secret is not None and (
            not isinstance(self.client_secret, str)
            or not 1 <= len(self.client_secret) <= 4096
            or _VISIBLE_ASCII.fullmatch(self.client_secret) is None
        ):
            raise ValueError("A valid confidential-client secret is required.")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(float(self.timeout_seconds))
            or not 0.1 <= float(self.timeout_seconds) <= 30.0
        ):
            raise ValueError("Token endpoint timeout must be between 0.1 and 30 seconds.")
        if (
            isinstance(self.max_response_bytes, bool)
            or not isinstance(self.max_response_bytes, int)
            or not 128 <= self.max_response_bytes <= 65536
        ):
            raise ValueError("Token response limit must be between 128 and 65536 bytes.")
        if self.transport is not None and not isinstance(self.transport, httpx.BaseTransport):
            raise TypeError("A synchronous HTTPX transport is required.")
        object.__setattr__(self, "token_endpoint", endpoint)
        object.__setattr__(self, "redirect_uri", redirect_uri)

    def exchange(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> OIDCTokenResponse:
        """Perform one bounded exchange without exposing provider errors."""
        if (
            not isinstance(code, str)
            or not 1 <= len(code) <= 4096
            or _VISIBLE_ASCII.fullmatch(code) is None
            or not isinstance(code_verifier, str)
            or _PKCE_VERIFIER.fullmatch(code_verifier) is None
            or not isinstance(redirect_uri, str)
            or redirect_uri != self.redirect_uri
        ):
            raise OIDCBrowserLoginError("OIDC authorization-code exchange was not accepted.")

        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "code_verifier": code_verifier,
        }
        headers = {"Accept": "application/json"}
        if self.client_secret is None:
            form["client_id"] = self.client_id
        else:
            # RFC 6749 client_secret_basic uses form-encoded credentials before
            # base64 encoding. Do not place the secret in the request body.
            credentials = (
                f"{quote_plus(self.client_id, safe='')}:"
                f"{quote_plus(self.client_secret, safe='')}"
            ).encode("ascii")
            headers["Authorization"] = "Basic " + base64.b64encode(credentials).decode("ascii")

        body = bytearray()
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=httpx.Timeout(float(self.timeout_seconds)),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                with client.stream(
                    "POST",
                    self.token_endpoint,
                    data=form,
                    headers=headers,
                    follow_redirects=False,
                ) as response:
                    if response.status_code != 200:
                        raise OIDCBrowserLoginError(
                            "OIDC authorization-code exchange failed."
                        )
                    content_type = response.headers.get("content-type", "")
                    if content_type.split(";", 1)[0].strip().casefold() != "application/json":
                        raise OIDCBrowserLoginError(
                            "OIDC token response was not accepted."
                        )
                    content_length = response.headers.get("content-length")
                    if content_length is not None:
                        if not content_length.isdigit() or int(content_length) > self.max_response_bytes:
                            raise OIDCBrowserLoginError(
                                "OIDC token response exceeded its size limit."
                            )
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > self.max_response_bytes:
                            raise OIDCBrowserLoginError(
                                "OIDC token response exceeded its size limit."
                            )
        except OIDCBrowserLoginError:
            raise
        except Exception:
            # Do not propagate endpoint, TLS, timeout, transport or response data.
            raise OIDCBrowserLoginError(
                "OIDC authorization-code exchange failed."
            ) from None

        try:
            payload = json.loads(
                bytes(body),
                object_pairs_hook=_reject_duplicate_json_keys,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise OIDCBrowserLoginError("OIDC token response was not accepted.") from None

        if not isinstance(payload, dict):
            raise OIDCBrowserLoginError("OIDC token response was not accepted.")
        id_token = payload.get("id_token")
        access_token = payload.get("access_token")
        token_type = payload.get("token_type")
        if (
            not _valid_token(id_token)
            or not _valid_token(access_token)
            or not isinstance(token_type, str)
            or token_type.casefold() != "bearer"
        ):
            raise OIDCBrowserLoginError("OIDC token response was not accepted.")
        return OIDCTokenResponse(
            id_token=id_token,
            access_token=access_token,
            token_type="Bearer",
        )
