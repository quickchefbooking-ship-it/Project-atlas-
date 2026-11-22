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
| #82 worker/OIDC compatibility probe | `7aa6e9b` | 44178610630 | success | 1174 passed | mergeable draft; run verified against PR #64 base, not PR #82 combined base |

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
