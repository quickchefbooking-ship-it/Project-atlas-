# THE PROFESSOR — CI Evidence Matrix

**Checked:** 2026-11-22  
**Important:** These are exact-head GitHub Actions test results. Passing CI proves the branch test suite ran successfully; it does not prove branch integration, production deployment, live provider connectivity, or runtime availability.

| PR / branch | Verified head (short) | Run | Result | Tests | State |
|---|---|---:|---|---:|---|
| #1 baseline repair | `f8d6eac` | 43489002177 | success | 237 passed | draft / unmerged |
| #46 session-conversation integration | `e0bc692` | 44095270221 | success | 925 passed | draft / unmerged |
| #47 chat capability gate | `1fc36ea` | 44095274919 | success | 926 passed | draft / unmerged |
| #48 prompt budget | `2f0e678` | 44475448752 | success | 929 passed | draft / unmerged |
| #49 login-readiness gate | `5dc77c9` | 44106252411 | success | 929 passed | draft / unmerged |
| #11 reasoning provider + identity/tenant stack | `fd52e01` | 43733864615 | success | 781 passed | draft / unmerged |
| #62 durable cancellation | `ec0101d` | 44135563861 | success | 1151 passed | draft / unmerged |
| #63 OIDC startup composition | `167f998` | 44167021419 | success | 1101 passed | draft / unmerged |
| #64 worker host readiness | `7aa6e9b` | 44178610630 | success | 1174 passed | draft / unmerged |
| #76 response contract | `40c4395` | 44390312814 | success | 289 passed | draft / unmerged |
| #79 explicit feedback candidate | `afb962c` | 45046430157 | success | 783 passed | draft / unmerged |
| #80 lesson → pending memory proposal | `2798b19` | 45046596722 | success | 786 passed | draft / unmerged |
| #81 chat/provider + learning integration | `2798b19` | 45046596722 | success | 786 passed | draft / unmerged; base #48 |
| #82 worker/OIDC + learning integration (NOT chat/provider) | `7aa6e9b` | 45046895853 | success | 1179 passed | exact PR #82 merge ref; base #80; draft/unmerged |
| #83 release-readiness false-positive guard tests | `d101a63` | 45049237138 | success | 1181 passed | PR #83 merge ref (worker + learning base, not chat); draft/unmerged; 2 additional readiness tests |

## Confirmed integration coverage
- #46–#48: session/conversation integration, explicit chat capability, bounded prompt composition.
- #11: opt-in provider composition, verified identity, tenant conversation/memory/evaluation/lesson/audit repositories and lifecycle tests.
- #79–#80: explicit negative feedback → pending candidate → independent review → owner-controlled pending memory proposal → separate memory approval before retrieval.

## Remaining verification gaps
1. Draft stacks are not merged; some are based on different parent branches. CI results are not proof that all branches compose together.
2. No live reasoning-provider round trip has been verified; provider configuration remains opt-in.
3. No verified deployment/startup parity or iPhone/browser end-to-end test against a running deployed instance.
4. Identity/RBAC/tenant boundaries and trusted-proxy/OIDC composition need cross-stack review; shared API-key auth in baseline is not verified identity.
5. Worker execution remains gated; no free host/isolation proof or unattended worker runtime.
6. Learning changes are tested on drafts; not deployed or merged into main.

## Next
- Finish the cross-stack dependency/reconciliation review.
- Verify one complete authenticated conversation: login/verified principal → chat → provider → stored conversation → audit → explicit evaluation → pending lesson → independent approval → owner memory proposal → second approval → approved memory retrieved into next conversation.
- Keep production/deployment/merge approval gates intact.

### Combined integration evidence
- PR #81 exact pull-request merge ref was tested in run 45046847109. Checkout log confirms `refs/remotes/pull/81/merge`; 786 passed, 1 warning in 24.38s. This combines chat/provider (#48) with governed learning (#80).
- PR #82 exact pull-request merge ref was tested in run 45046895853. Checkout log confirms `refs/remotes/pull/82/merge`; 1179 passed, 1 warning in 25.86s. This combines worker/OIDC readiness (#64) with learning (#80), but **not PR #81 chat/provider base**.
- PR #84 is the new full-stack probe targeting PR #48's chat/provider branch with the PR #82 worker+learning integration. CI evidence is pending; do not claim three-way integration until its merge-ref run is verified. Still no merge/deployment.

### PR #83 — readiness regression guard
- Exact head `d101a6303422e2b73028847c5d6bbac97cf95fe3`, run 45049237138 succeeded: **1181 passed, 1 warning in 21.30s**.
- Adds tests that missing launch configuration reports blockers, and that configured identity/storage/provider still cannot claim readiness without verified live provider round-trip evidence. No runtime code changes.

### Ancestry correction (2026-11-22)
- PR #81 base is PR #48; head is PR #80. Run 45046847109 explicitly checked out PR #81's merge ref and passed 786 tests.
- PR #82 base is PR #80; head is PR #64. Its 1179-test pass is worker/OIDC + learning, not chat/provider.
- PR #83 base is PR #80; it tests launch-readiness safeguards on worker + learning. It is not full-stack chat integration.
- PR #84 is the corrected full-stack probe. Its CI must be checked against the exact merge ref before P4 is complete.
