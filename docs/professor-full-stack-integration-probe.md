# Professor full-stack integration probe

This branch combines:
- PR #48: chat session/capability/prompt-budget integration;
- PR #80: governed learning candidate → reviewed lesson → owner-controlled memory proposal → second approval;
- PR #64: worker/OIDC readiness and execution safety stack.

## Why this probe exists
PR #82's base was PR #80, not PR #81, so its 1,179-test result was not proof that chat/provider, learning, and worker-readiness changes were all present in the same tested merge ref. PR #81 separately integrates PR #48 with PR #80. This probe combines PR #81's chat/provider base with the PR #82 worker-readiness integration.

## Verification goal
- Mergeability and exact PR merge-ref CI.
- Tests must run against the PR merge ref, not just the branch head.
- Review failures and conflicts before considering any merge.
- No merge, deployment, or capability activation.

## Expected safe defaults
- Paid AI off.
- Reasoning provider off unless explicitly configured.
- Capability execution disabled.
- No external writes or task-supplied handlers.
- Runtime and real provider/login round-trip remain unverified by CI.

**Draft integration probe only.**


## Merge-candidate checkpoint (2026-11-22)

- Candidate branch: `atlas/professor-full-stack-merge-candidate-2026-11-22`
- Merge commit: `54dc795a7f7508a7c48f98748d48351dd0d4bcdf`
- Two parents: chat/provider base `2f0e678a2a403502bce712d34d8e7917a01edf10` and full-stack integration head `5c2549e185b93448340ca52be0156e77e5ab4a94`.
- GitHub mergeability: **mergeable**.
- Exact merge commit status: **no workflow runs / no completed checks observed**.
- Workflow is configured for push to `atlas/**` and pull_request. Candidate branch name matches push trigger. This documentation-only checkpoint commit is intended to cause a fresh push event and provide CI evidence; no production action.


## Test coverage audit checkpoint

Read-only review of test files on the candidate branch:

- Chat UI: bearer API usage, route serving, provider metadata/failure behavior, deletion-retention disclosure.
- Reasoning pipeline: two-pass reasoning, user context treated as reference, critique holds, clarification/provider gating, external action approval, blueprint validation, bounded memory/history, prompt-injection resilience, provider contracts/metadata, structured history, memory conflict precedence.
- Worker: lifecycle/readiness, disabled-by-default, registered local step only, kill switch, unsupported capabilities, scopes, identity/isolation proof, tenant grant, cancellation, drain/dispatch admission and result commit.
- OIDC browser flow: hosted session/CSRF/logout, unlinked subject fail-closed, callback replay protection.
- Execution HTTP: bounded execution, kill switch, default-off configuration, scope checks, external capability denial, Crossref evidence chain, membership recheck, audit reservation ordering/failure blocking.
- Security: private-route authentication, API-key configuration, route dependency coverage, bounded intake, finite criteria, loopback development binding, no shared-key human identity, proposal review disabled pending verified identity, readiness does not overclaim provider verification.

This is a **file/test-name audit**, not a test execution. Combined CI remains unverified.

## Known blockers retained
- API shared-key is not verified human identity/RBAC/tenant isolation.
- SQLite single-host persistence is not distributed.
- Worker execution is not independently isolated; execution remains disabled pending proof.
- No unattended retry dispatcher.
- Cooperative cancellation is not hard-kill.
- Capability registry does not dynamically load plugins.
- Temporary pytest runner is not an OS security sandbox.
- No live runtime/provider/OIDC round-trip verification.
