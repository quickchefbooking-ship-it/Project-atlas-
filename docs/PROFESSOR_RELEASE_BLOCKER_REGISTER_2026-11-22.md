# THE PROFESSOR — Release Blocker Register (2026-11-22)

**Status:** P5 blocked. This register distinguishes verified code/configuration gaps from runtime checks not yet performed.

## Verified blockers

| ID | Blocker | Evidence / current default | Required closure evidence |
|---|---|---|---|
| R1 | No verified runtime smoke test | No runtime execution from this build session; docs-only prep completed | Startup on a safe host, health endpoints, UI render, exact commit SHA and logs (redacted) |
| R2 | Reasoning provider is off | `ATLAS_LLM_PROVIDER=off` default; provider config is opt-in | A real local/self-hosted provider conversation, response, latency/error evidence; no paid provider without approval |
| R3 | Verified identity not proven in live configuration | API key is shared-secret; OIDC verifier/login readiness reports configuration only | Test login/callback/logout; verified tenant principal and cross-tenant denial; secrets never in evidence |
| R4 | Hosted login configuration/services unverified | `/identity/login-readiness` is diagnostic; routes/services/config may be absent | Exact readiness response plus successful hosted OIDC round trip in controlled environment |
| R5 | Tenant storage setup not verified | `/launch/readiness` checks tenant storage path presence only | Safe database creation, schema initialization, tenant isolation tests, backup/restore evidence |
| R6 | Worker execution must remain gated and isolated | Capability execution is opt-in, but the current bounded `execute-next` path dispatches registered handlers in the API process; Crossref network work also runs in-process. Worker-host readiness is a gate, not proof that an isolated execution host exists. | Document host, isolation, process boundaries, limits, kill/recovery behavior; move network-capable work to an independently isolated host and prove it; explicit approval before enabling |
| R7 | Capability scope remains narrow | Trusted handlers are application-installed; bounded math and read-only Crossref research are current sample verticals | Demonstrate desired core workflow against allowed capabilities; expansion requires separate review |
| R8 | iPhone Safari end-to-end not verified | Browser UI code exists, but no device/runtime check performed | iPhone Safari screenshot/recorded checks: sign-in, conversation, persistence, error state, accessibility/layout |
| R9 | Release/rollback operations not exercised | Checklist prepared only; no deployment | Release owner, staging, monitoring, backup, rollback rehearsal and sign-off |

## Safe order to close blockers
1. R1: run local loopback smoke with provider off and execution disabled.
2. R5: verify local tenant store initialization and isolation with tests.
3. R2: enable a local self-hosted reasoning provider only after its endpoint is on the same trusted machine/network and test a real conversation.
4. R3/R4: configure OIDC in a controlled test environment and verify full login/callback/logout plus tenant-denial cases.
5. R6/R7: worker isolation proof and capability safety review. The current in-process network handler is a known isolation gap. Keep execution disabled until separately approved.
6. R8: iPhone Safari UX check against safe staging.
7. R9: release and rollback rehearsal.

## Explicitly not approved
- Public deployment or public tunnel.
- Paid AI/provider use.
- Enabling worker/capability execution.
- Production migrations, merges, source transfers or secrets changes.
- Financial, social, email, messaging or other external write integrations.

**Completion rule:** A blocker may be closed only with the exact evidence described above. Configuration flags or CI alone do not close live-runtime blockers.
