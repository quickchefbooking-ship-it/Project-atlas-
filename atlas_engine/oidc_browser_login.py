"""Provider-neutral OIDC callback orchestration for Atlas browser login.

This service composes the existing one-time PKCE transaction, pinned ID-token
verifier, explicit account link and Atlas session services. It deliberately
does not expose HTTP routes or cookies; a later route must call this service
with callback parameters and set only the returned Atlas-owned credentials.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit

from .oidc_id_token_verifier import VerifiedIDTokenClaims
from .oidc_jwt_verifier import OIDCVerifierUnavailable
from .oidc_login_session import IssuedOIDCBrowserSession, OIDCLoginSessionService
from .oidc_login_transaction import SQLiteOIDCLoginTransactionStore


MAX_AUTHORIZATION_CODE_LENGTH = 4096
MAX_ID_TOKEN_LENGTH = 8192
MAX_ACCESS_TOKEN_LENGTH = 8192
_VISIBLE_TOKEN = re.compile(r"^[\x21-\x7e]+$")


class OIDCBrowserLoginError(RuntimeError):
    """The callback could not safely complete an Atlas browser login."""


@dataclass(frozen=True)
class OIDCTokenResponse:
    """Minimal code-exchange result; credentials are never included in repr."""

    id_token: str = field(repr=False)
    access_token: str = field(repr=False)
    token_type: str = "Bearer"


class AuthorizationCodeExchanger(Protocol):
    """Trusted adapter for one deployment-pinned OIDC token endpoint."""

    def exchange(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> OIDCTokenResponse:
        """Exchange a one-time code using the server-held PKCE verifier."""
        ...


class IDTokenVerifier(Protocol):
    """Trusted verifier for the registered OIDC browser client."""

    def verify(
        self,
        id_token: str,
        *,
        access_token: str | None = None,
    ) -> VerifiedIDTokenClaims:
        """Verify signature and registered ID-token claims."""
        ...


def _validate_redirect_uri(value: str) -> str:
    """Accept only a fixed deployment-owned HTTPS callback URI."""
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 2048
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError("A fixed HTTPS OIDC redirect URI is required.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("A fixed HTTPS OIDC redirect URI is required.") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port == 0
    ):
        raise ValueError("A fixed HTTPS OIDC redirect URI is required.")
    return value


def _validate_authorization_code(code: str) -> str:
    """Bound and reject malformed callback codes before contacting the provider."""
    if (
        not isinstance(code, str)
        or not 1 <= len(code) <= MAX_AUTHORIZATION_CODE_LENGTH
        or not _VISIBLE_TOKEN.fullmatch(code)
    ):
        raise OIDCBrowserLoginError("OIDC callback could not be completed.")
    return code


def _validate_token_response(tokens: object) -> OIDCTokenResponse:
    """Accept only a bounded bearer token response from the trusted adapter."""
    if not isinstance(tokens, OIDCTokenResponse):
        raise OIDCBrowserLoginError("OIDC token response was not accepted.")
    if (
        not isinstance(tokens.id_token, str)
        or not 1 <= len(tokens.id_token) <= MAX_ID_TOKEN_LENGTH
        or not _VISIBLE_TOKEN.fullmatch(tokens.id_token)
        or not isinstance(tokens.access_token, str)
        or not 1 <= len(tokens.access_token) <= MAX_ACCESS_TOKEN_LENGTH
        or not _VISIBLE_TOKEN.fullmatch(tokens.access_token)
        or not isinstance(tokens.token_type, str)
        or tokens.token_type.casefold() != "bearer"
    ):
        raise OIDCBrowserLoginError("OIDC token response was not accepted.")
    return tokens


@dataclass(frozen=True)
class OIDCBrowserLoginService:
    """Consume callback state, exchange the code, verify identity and issue a session.

    The transaction store must be the exact same trusted instance used by the
    account-link service. This ensures the nonce digest checked during account
    resolution belongs to the state that this callback consumed.
    """

    transactions: SQLiteOIDCLoginTransactionStore
    exchanger: AuthorizationCodeExchanger
    id_token_verifier: IDTokenVerifier
    login_sessions: OIDCLoginSessionService
    redirect_uri: str

    def __post_init__(self) -> None:
        if not isinstance(self.transactions, SQLiteOIDCLoginTransactionStore):
            raise TypeError("A trusted OIDC login transaction store is required.")
        if not isinstance(self.login_sessions, OIDCLoginSessionService):
            raise TypeError("A trusted Atlas OIDC login-session service is required.")
        if self.login_sessions.account_links.transactions is not self.transactions:
            raise ValueError(
                "OIDC callback and account-link services must share one transaction store."
            )
        if not callable(getattr(self.exchanger, "exchange", None)):
            raise TypeError("A trusted OIDC authorization-code exchanger is required.")
        if not callable(getattr(self.id_token_verifier, "verify", None)):
            raise TypeError("A trusted OIDC ID-token verifier is required.")
        object.__setattr__(self, "redirect_uri", _validate_redirect_uri(self.redirect_uri))

    def complete_callback(self, code: str, state: str) -> IssuedOIDCBrowserSession:
        """Complete one callback without accepting identity or redirect data from the browser.

        State is consumed before code exchange. Any provider, token-verification,
        account-link or membership failure therefore leaves the transaction
        unusable and cannot be replayed to obtain a second session.
        """
        transaction = self.transactions.consume(state)
        authorization_code = _validate_authorization_code(code)

        try:
            token_response = self.exchanger.exchange(
                authorization_code,
                transaction.code_verifier,
                self.redirect_uri,
            )
        except Exception:
            # Provider errors can contain endpoint details, codes or credentials.
            raise OIDCBrowserLoginError(
                "OIDC authorization-code exchange failed."
            ) from None

        tokens = _validate_token_response(token_response)
        try:
            claims = self.id_token_verifier.verify(
                tokens.id_token,
                access_token=tokens.access_token,
            )
        except OIDCVerifierUnavailable:
            raise
        except Exception:
            raise OIDCBrowserLoginError(
                "OIDC identity token was not accepted."
            ) from None

        if not isinstance(claims, VerifiedIDTokenClaims):
            raise OIDCBrowserLoginError("OIDC identity token was not accepted.")

        # The session service rechecks the consumed transaction nonce, explicit
        # account link, active account, unique tenant membership and CSRF setup.
        return self.login_sessions.complete_login(claims, transaction)
