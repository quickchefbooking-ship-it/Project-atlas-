# THE PROFESSOR — Live Release Smoke Checklist

**Status:** Prepared; not run against a live deployment.  
**Current branch evidence (2026-11-22):** PR #85 merge-ref CI run [45062228181](https://github.com/quickchefbooking-ship-it/Project-atlas-/actions/runs/45062228181) passed **1189 tests, 1 warning** for head `f26cda77b83305a516a189d6ff4403e984cc8561` on base `c58f5856ed5a557c4deaa02333f5ec4e89825ecb` (matching push run [45062223936](https://github.com/quickchefbooking-ship-it/Project-atlas-/actions/runs/45062223936)). This is branch-level evidence, not runtime/deployment proof. PR #84 is diverged from PR #48 (143 ahead / 3 behind; four overlapping files differ), so PR #85 is not a clean release source. PR #63 hosted-login composition and PR #83 readiness-test branches are separate drafts with their own passing CI; they are not included in PR #85.

## Gate 0 — Approval and environment
- [ ] Ashley explicitly approves a deployment/runtime test environment and the target.
- [ ] Confirm free/self-hosted target and cost before starting.
- [ ] Maintainer selects a clean, review-approved source branch. Do not run the PR #85 draft as a release source until its base integration/conflicts are reconciled.
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
- Hosted login composition is a separate draft PR #63; it is not in PR #85's base. Startup services remain unset on the current integration branch.
- PR #84/#85 integration is diverged from PR #48 prompt-budget base; no canonical clean test source has been selected.
- No live provider round-trip verified.
- No deployed startup/build-revision parity verified.
- No iPhone Safari live deployment test verified.
- No production/merge/deployment approval recorded.
