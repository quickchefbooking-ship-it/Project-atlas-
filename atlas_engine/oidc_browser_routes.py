"""Fail-closed FastAPI routes for hosted Atlas OIDC browser login.

Provider endpoints and callback services are injected by trusted server startup
code. Browser input cannot choose an issuer, endpoint, redirect URI, account,
tenant, role, or permission. No provider is selected by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from .atlas_session_identity import AtlasSessionIdentityService
from .http_identity import ATLAS_SESSION_COOKIE, require_verified_principal
from .oidc_jwt_verifier import OIDCVerifierUnavailable
from .oidc_login_transaction import SQLiteOIDCLoginTransactionStore

ATLAS_CSRF_COOKIE = "__Host-atlas_csrf"
CALLBACK_PATH = "/identity/callback"
CHAT_PATH = "/professor/chat"
MAX_AUTHORIZATION_URL_LENGTH = 8192
_RESERVED_AUTHORIZATION_PARAMETERS = frozenset(
    {
        "response_type",
        "client_id",
        "redirect_uri",
        "scope",
        "state",
        "nonce",
        "code_challenge",
        "code_challenge_method",
    }
)


def _validate_https_url(value: str, *, allow_query: bool) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 2048
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
        or "\\" in value
    ):
        raise ValueError("A deployment-pinned HTTPS OIDC URL is required.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("A deployment-pinned HTTPS OIDC URL is required.") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port == 0
        or (not allow_query and parsed.query)
    ):
        raise ValueError("A deployment-pinned HTTPS OIDC URL is required.")
    return value


def _origin_from_redirect_uri(value: str) -> str:
    parsed = urlsplit(value)
    host = parsed.hostname
    if not host:
        raise ValueError("A fixed HTTPS callback origin is required.")
    port = parsed.port
    suffix = f":{port}" if port is not None and port != 443 else ""
    return f"https://{host.lower()}{suffix}"


@dataclass(frozen=True)
class OIDCBrowserLoginInitiator:
    """Build a fixed Authorization Code + PKCE redirect using server state."""

    transactions: SQLiteOIDCLoginTransactionStore
    authorization_endpoint: str
    client_id: str
    redirect_uri: str

    def __post_init__(self) -> None:
        if not isinstance(self.transactions, SQLiteOIDCLoginTransactionStore):
            raise TypeError("A trusted OIDC login transaction store is required.")
        authorization_endpoint = _validate_https_url(
            self.authorization_endpoint, allow_query=True
        )
        redirect_uri = _validate_https_url(self.redirect_uri, allow_query=False)
        if urlsplit(redirect_uri).path != CALLBACK_PATH:
            raise ValueError("The OIDC redirect URI must target the Atlas callback route.")
        if (
            not isinstance(self.client_id, str)
            or not 1 <= len(self.client_id) <= 256
            or any(ord(char) < 0x21 or ord(char) > 0x7E for char in self.client_id)
        ):
            raise ValueError("A bounded registered OIDC client ID is required.")

        existing = parse_qsl(urlsplit(authorization_endpoint).query, keep_blank_values=True)
        if any(key in _RESERVED_AUTHORIZATION_PARAMETERS for key, _ in existing):
            raise ValueError("The authorization endpoint contains reserved OIDC parameters.")

        object.__setattr__(self, "authorization_endpoint", authorization_endpoint)
        object.__setattr__(self, "redirect_uri", redirect_uri)

    def begin_login(self) -> str:
        """Create one server-side transaction and return its provider redirect URL."""
        transaction = self.transactions.begin()
        parsed = urlsplit(self.authorization_endpoint)
        parameters = parse_qsl(parsed.query, keep_blank_values=True)
        parameters.extend(
            [
                ("response_type", "code"),
                ("client_id", self.client_id),
                ("redirect_uri", self.redirect_uri),
                ("scope", "openid"),
                ("state", transaction.state),
                ("nonce", transaction.nonce),
                ("code_challenge", transaction.code_challenge),
                ("code_challenge_method", "S256"),
            ]
        )
        location = urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(parameters),
                "",
            )
        )
        if len(location) > MAX_AUTHORIZATION_URL_LENGTH:
            raise ValueError("The configured OIDC authorization URL is too long.")
        return location


router = APIRouter()


def _login_components(request: Request):
    state = request.app.state
    initiator = getattr(state, "oidc_login_initiator", None)
    callback = getattr(state, "oidc_browser_login_service", None)
    if (
        not isinstance(initiator, OIDCBrowserLoginInitiator)
        or not callable(getattr(callback, "complete_callback", None))
        or getattr(callback, "transactions", None) is not initiator.transactions
        or getattr(callback, "redirect_uri", None) != initiator.redirect_uri
        or getattr(callback, "login_sessions", None) is None
    ):
        raise HTTPException(
            status_code=503,
            detail="Hosted sign-in is not configured.",
        )
    return initiator, callback


def _session_max_age(absolute_expires_at: object) -> int:
    if not isinstance(absolute_expires_at, str):
        raise ValueError("A valid Atlas session expiry is required.")
    try:
        expiry = datetime.fromisoformat(absolute_expires_at)
    except ValueError:
        raise ValueError("A valid Atlas session expiry is required.") from None
    if expiry.tzinfo is None:
        raise ValueError("A timezone-aware Atlas session expiry is required.")
    remaining = int((expiry.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds())
    if remaining < 1:
        raise ValueError("The Atlas session has already expired.")
    return min(remaining, 30 * 24 * 60 * 60)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"


@router.get("/identity/login", include_in_schema=False)
def identity_login(request: Request):
    """Start a server-generated Authorization Code + PKCE transaction."""
    initiator, _callback = _login_components(request)
    try:
        location = initiator.begin_login()
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Hosted sign-in is temporarily unavailable.",
        ) from None
    response = RedirectResponse(location, status_code=302)
    _no_store(response)
    return response


@router.get("/identity/callback", include_in_schema=False)
def identity_callback(
    request: Request,
    code: str | None = Query(default=None, max_length=4096),
    state: str | None = Query(default=None, max_length=256),
    error: str | None = Query(default=None, max_length=128),
):
    """Consume one callback and establish only an Atlas-owned browser session."""
    initiator, callback = _login_components(request)
    if not state:
        raise HTTPException(status_code=400, detail="Sign-in could not be completed.")

    if error is not None or not code:
        # Even provider-denied or incomplete callbacks consume valid state.
        try:
            callback.transactions.consume(state)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail="Sign-in was not completed.")

    try:
        issued = callback.complete_callback(code, state)
    except OIDCVerifierUnavailable:
        raise HTTPException(
            status_code=503,
            detail="Identity verification is temporarily unavailable.",
        ) from None
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Sign-in could not be completed.",
        ) from None

    session = getattr(issued, "session", None)
    session_token = getattr(session, "token", None)
    csrf_token = getattr(issued, "csrf_token", None)
    login_sessions = callback.login_sessions
    sessions = getattr(login_sessions, "sessions", None)
    memberships = getattr(login_sessions, "memberships", None)
    if (
        not isinstance(session_token, str)
        or not 40 <= len(session_token) <= 256
        or not isinstance(csrf_token, str)
        or not 40 <= len(csrf_token) <= 256
        or sessions is None
        or memberships is None
    ):
        if isinstance(session_token, str) and callable(getattr(sessions, "revoke_session", None)):
            try:
                sessions.revoke_session(session_token)
            except Exception:
                pass
        raise HTTPException(status_code=503, detail="Atlas browser session could not be established.")

    try:
        max_age = _session_max_age(getattr(session, "absolute_expires_at", None))
        session_identity = AtlasSessionIdentityService(sessions, memberships)
        trusted_origin = _origin_from_redirect_uri(initiator.redirect_uri)
    except Exception:
        try:
            sessions.revoke_session(session_token)
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="Atlas browser session could not be established.") from None

    request.app.state.atlas_session_identity_service = session_identity
    request.app.state.atlas_trusted_origins = frozenset({trusted_origin})

    response = RedirectResponse(CHAT_PATH, status_code=303)
    response.set_cookie(
        key=ATLAS_SESSION_COOKIE,
        value=session_token,
        max_age=max_age,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )
    # The CSRF token is intentionally readable by same-origin application code;
    # unsafe requests must echo it in X-Atlas-CSRF and pass the exact Origin check.
    response.set_cookie(
        key=ATLAS_CSRF_COOKIE,
        value=csrf_token,
        max_age=max_age,
        secure=True,
        httponly=False,
        samesite="lax",
        path="/",
    )
    _no_store(response)
    return response


@router.post("/identity/logout", include_in_schema=False)
def identity_logout(
    request: Request,
    _principal=Depends(require_verified_principal),
):
    """Revoke the current Atlas browser session after Origin and CSRF checks."""
    session_token = request.cookies.get(ATLAS_SESSION_COOKIE)
    if not isinstance(session_token, str) or not session_token:
        raise HTTPException(status_code=401, detail="Atlas browser session is required.")
    identity_service = getattr(request.app.state, "atlas_session_identity_service", None)
    sessions = getattr(identity_service, "sessions", None)
    if not callable(getattr(sessions, "revoke_session", None)):
        raise HTTPException(status_code=503, detail="Atlas session service is unavailable.")
    try:
        sessions.revoke_session(session_token)
    except Exception:
        raise HTTPException(status_code=503, detail="Atlas session could not be revoked.") from None

    response = Response(status_code=204)
    response.delete_cookie(
        key=ATLAS_SESSION_COOKIE,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        key=ATLAS_CSRF_COOKIE,
        path="/",
        secure=True,
        httponly=False,
        samesite="lax",
    )
    _no_store(response)
    return response
