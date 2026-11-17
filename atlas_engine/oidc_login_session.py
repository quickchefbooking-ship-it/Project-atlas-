"""Compose a verified OIDC identity into an Atlas-owned browser session.

This provider-neutral service deliberately stops before HTTP response handling:
it never sets cookies, selects an identity provider, exchanges an authorization
code, or enables a public login route. It resolves an explicit external link,
requires one active Atlas tenant membership, then issues an opaque Atlas session
and a session-bound CSRF token for trusted callback code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .atlas_session_identity import (
    ATLAS_IDENTITY_ISSUER,
    AtlasSessionIdentityService,
)
from .identity_policy import RequestPrincipal
from .oidc_account_link import OIDCAccountLinkService
from .oidc_id_token_verifier import VerifiedIDTokenClaims
from .oidc_login_transaction import ConsumedLoginTransaction
from .session_identity import IssuedSession, SQLiteSessionRepository
from .tenant_membership import SQLiteMembershipRegistry
from .verified_identity import VerifiedIdentity, principal_from_verified_identity


class OIDCLoginSessionError(RuntimeError):
    """The verified identity could not be safely converted into an Atlas session."""


class OIDCLoginSessionCleanupError(OIDCLoginSessionError):
    """An incomplete login session could not be revoked after an issuance failure."""


@dataclass(frozen=True)
class IssuedOIDCBrowserSession:
    """Trusted callback result; raw session and CSRF credentials are redacted from repr."""

    session: IssuedSession = field(repr=False)
    csrf_token: str = field(repr=False)
    principal: RequestPrincipal = field(repr=False)


@dataclass(frozen=True)
class OIDCLoginSessionService:
    """Resolve explicit OIDC account links into existing Atlas sessions."""

    account_links: OIDCAccountLinkService
    sessions: SQLiteSessionRepository
    memberships: SQLiteMembershipRegistry

    def __post_init__(self) -> None:
        if not isinstance(self.account_links, OIDCAccountLinkService):
            raise TypeError("A trusted OIDC account-link service is required.")
        if not isinstance(self.sessions, SQLiteSessionRepository):
            raise TypeError("A trusted Atlas session repository is required.")
        if not isinstance(self.memberships, SQLiteMembershipRegistry):
            raise TypeError("A trusted tenant membership registry is required.")

        account_database = Path(
            self.account_links.repository.accounts.database_path
        ).resolve()
        session_database = Path(self.sessions.database_path).resolve()
        if account_database != session_database:
            raise ValueError(
                "Atlas account links and browser sessions must share the account database."
            )

    def complete_login(
        self,
        claims: VerifiedIDTokenClaims,
        transaction: ConsumedLoginTransaction,
    ) -> IssuedOIDCBrowserSession:
        """Issue an Atlas session only after identity, nonce and membership checks.

        The caller must already have consumed the one-time callback state and
        verified the ID token with the pinned OIDC verifier. Account resolution
        rechecks the transaction nonce. Tenant and scopes come only from the
        Atlas membership registry, never from provider claims or browser input.
        """
        linked = self.account_links.resolve_login_account(claims, transaction)
        identity = VerifiedIdentity(
            issuer=ATLAS_IDENTITY_ISSUER,
            subject=linked.account_id,
        )
        expected_principal = principal_from_verified_identity(identity, self.memberships)
        if (
            expected_principal.issuer != ATLAS_IDENTITY_ISSUER
            or expected_principal.subject != linked.account_id
            or not expected_principal.membership_active
        ):
            raise OIDCLoginSessionError("An active Atlas tenant membership is required.")

        issued: IssuedSession | None = None
        try:
            issued = self.sessions.issue_session(linked.account_id)

            # Re-resolve after issuance to catch membership revocation or
            # tenant/scope changes between preflight and session creation.
            current_principal = AtlasSessionIdentityService(
                self.sessions, self.memberships
            ).authenticate(issued.token)
            if current_principal != expected_principal:
                raise OIDCLoginSessionError(
                    "Atlas tenant membership changed during login; retry sign-in."
                )

            csrf_token = self.sessions.issue_csrf_token(issued.token)
            if not isinstance(csrf_token, str) or not 40 <= len(csrf_token) <= 256:
                raise OIDCLoginSessionError("A valid session-bound CSRF token was not issued.")

            return IssuedOIDCBrowserSession(
                session=issued,
                csrf_token=csrf_token,
                principal=current_principal,
            )
        except Exception:
            if issued is not None:
                try:
                    self.sessions.revoke_session(issued.token)
                except Exception:
                    raise OIDCLoginSessionCleanupError(
                        "An incomplete Atlas browser session could not be revoked."
                    ) from None
            raise
