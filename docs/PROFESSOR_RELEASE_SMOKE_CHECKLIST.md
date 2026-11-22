# THE PROFESSOR — Live Release Smoke Checklist

**Status:** Prepared; not run against a live deployment.  
**Current branch evidence:** PR #82 merge-ref CI passed 1179 tests, but this is not deployment evidence.

## Gate 0 — Approval and environment
- [ ] Ashley explicitly approves a deployment/runtime test environment and the target.
- [ ] Confirm free/self-hosted target and cost before starting.
- [ ] Confirm test tenant/user and safe disposable data.
- [ ] No production migrations or external write integrations unless separately approved.

## Gate 1 — Configuration and secrets
- [ ] Set `ATLAS_API_REQUIRE_AUTH=true`.
- [ ] Generate/store a strong API key only in the deployment secret store; never echo or commit it.
- [ ] Confirm `ATLAS_CAPABILITY_EXECUTION_ENABLED=false` unless a separately reviewed test requires it.
- [ ] Confirm `ATLAS_ENABLE_PAID_AI=false`, `ATLAS_LLM_PROVIDER=off` by default.
- [ ] Configure verified OIDC identity, tenant membership store and hosted login services only using the approved deployment configuration.
- [ ] Confirm DB path is persistent and backed up.
- [ ] Confirm HTTPS, trusted-proxy configuration, firewall, and client IP handling.
- [ ] Set build revision to the full verified Git SHA.

## Gate 2 — Health and readiness
- [ ] `GET /health` returns live service status.
- [ ] `GET /build-info` returns the expected full revision (or clearly reports unknown).
- [ ] `GET /identity/login-readiness` accurately distinguishes configured from implemented/verified.
- [ ] `GET /launch/readiness` is reviewed; no blocker is falsely marked passed.
- [ ] Confirm provider round-trip check remains false until a real conversation is performed.

## Gate 3 — Identity, tenancy, and browser
- [ ] Sign in with a verified identity provider; verify `/identity/me` returns expected tenant/scopes.
- [ ] Test unauthenticated and wrong-tenant requests fail closed.
- [ ] Test conversation history isolation and deletion.
- [ ] Verify iPhone Safari chat loads, sends, displays failure state, and preserves/retries only where safe.
- [ ] Verify voice interface permissions and browser speech support; wake-word/continuous listening is not assumed.

## Gate 4 — Real reasoning (local provider preferred)
- [ ] If using a local model, run it on the same host as Atlas or use a secured HTTPS endpoint.
- [ ] Configure the exact local provider/model name; paid AI remains disabled.
- [ ] Perform a harmless first conversation and verify a real provider response.
- [ ] Perform a follow-up turn and verify conversation context persists.
- [ ] Check response provenance, provider/model diagnostics, and failure handling.
- [ ] Record a live provider round-trip result; only then set any release evidence to verified.

## Gate 5 — Governed learning
- [ ] Submit explicit negative feedback and confirm a pending candidate is created.
- [ ] Confirm candidate is linked to the evaluation and remains pending.
- [ ] Independent reviewer approves/rejects; proposer cannot self-review.
- [ ] Owner converts an approved candidate into a pending memory proposal.
- [ ] Confirm memory is not retrieved until its separate approval.
- [ ] Confirm approved memory appears in a bounded follow-up prompt and can be deleted/expired.

## Gate 6 — Safe task/worker boundaries
- [ ] Capability execution remains disabled unless explicitly approved for a controlled test.
- [ ] Verify cancellation/recovery states, lease fencing, and audit records.
- [ ] Confirm no unattended worker dispatch, retry, external action, or general plugin execution is enabled.
- [ ] Verify kill switch and rollback path.

## Gate 7 — Evidence and release decision
- [ ] Record test date, environment, exact full SHA, test operator, outcomes, and redacted logs.
- [ ] All failed checks are recorded as BLOCKED/FAILED, not hidden.
- [ ] Complete security review and release approval separately.
- [ ] Deployment/merge is not authorized by this checklist itself.

## Current known blockers
- Hosted login readiness reports services not yet configured/implemented in the current readiness code.
- No live provider round-trip verified.
- No deployed startup/build-revision parity verified.
- No iPhone Safari live deployment test verified.
- No production/merge/deployment approval recorded.
