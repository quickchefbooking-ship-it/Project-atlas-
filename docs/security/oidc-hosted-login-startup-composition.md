# Hosted OIDC startup composition

## Configuration contract

Hosted browser login remains unconfigured unless every required setting is
present:

| Setting | Purpose |
| --- | --- |
| `ATLAS_OIDC_ISSUER` | Exact HTTPS issuer for the selected provider |
| `ATLAS_OIDC_AUDIENCE` | Existing Atlas API audience used by bearer authentication |
| `ATLAS_OIDC_JWKS_URI` | Deployment-pinned HTTPS signing-key endpoint |
| `ATLAS_OIDC_ALLOWED_ALGORITHMS` | Explicit supported signing-algorithm allowlist |
| `ATLAS_OIDC_AUTHORIZATION_ENDPOINT` | Fixed HTTPS authorization endpoint |
| `ATLAS_OIDC_TOKEN_ENDPOINT` | Fixed HTTPS token endpoint |
| `ATLAS_OIDC_CLIENT_ID` | Registered browser-client identifier |
| `ATLAS_OIDC_REDIRECT_URI` | Exact HTTPS callback ending in `/identity/callback` |
| `ATLAS_ACCOUNT_DB_PATH` | Dedicated account, account-link and session database |
| `ATLAS_MEMBERSHIP_DB_PATH` | Dedicated server-controlled tenant membership database |
| `ATLAS_OIDC_LOGIN_TRANSACTION_DB_PATH` | Dedicated encrypted one-time PKCE transaction database |
| `ATLAS_OIDC_LOGIN_TRANSACTION_KEY_HEX` | Exactly 32 random bytes encoded as 64 hexadecimal characters |

`ATLAS_OIDC_CLIENT_SECRET` is optional. Set it only for a confidential
provider client; public clients use Authorization Code + PKCE without a
client secret. Do not place any secret or key value in source control.

## Storage and identity boundaries

The factory rejects path aliasing between account, membership and transaction
stores and the existing core or tenant database paths. It validates the
provider configuration, HTTPS endpoints, client, callback path and key before
initializing schemas.

The account database receives the account, session and explicit OIDC account
link schemas. The transaction database receives the encrypted one-time PKCE
transaction schema. The membership database is initialized or reused from the
existing verified identity service. These operations create schemas only:
they do not create accounts, link provider subjects, create tenants or grant
scopes.

A browser login can complete only for an already-linked external issuer/subject
and an active Atlas account with exactly one active server-provisioned tenant
membership under `atlas://identity`. No email matching or automatic linking
is permitted.

## Readiness semantics

- `not_configured`: one or more required verifier or browser-login settings are absent.
- `configuration_invalid`: all required setting names are present but trusted startup validation failed.
- `routes_registered_unconfigured`: routes exist but matching initiator/callback services are unavailable.
- `routes_registered_unverified`: matching services are composed; a real provider round trip is still unverified.

The `/launch/readiness` endpoint reports hosted login configured only when the
matching startup services exist. It continues to report the live provider
round trip as unverified and capability execution as disabled. Neither
configuration presence nor successful unit tests prove that Replit has been
configured or that a production sign-in works.

## Operational gate

Before hosted login is enabled in a deployment, an owner must select and
register the provider client, provision the exact callback URI, place the
database paths and 32-byte key in deployment-managed settings, provision
account links and Atlas memberships through reviewed administrative workflows,
and complete a real sign-in/callback/logout test. This PR does not set those
values, enable public login in Replit, change secrets or deploy.
