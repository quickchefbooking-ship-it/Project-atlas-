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
