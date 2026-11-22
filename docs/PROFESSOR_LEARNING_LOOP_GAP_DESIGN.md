# Professor Learning Loop — Gap and Safe Integration Design

**Status:** Draft design checkpoint (2026-11-22)  
**Scope:** Governed learning, not autonomous model training or self-modifying code.

## Existing verified components on PR #11
- Durable memory proposals scoped to verified tenant and owner.
- Explicit approval/rejection, bounded text and retention, expiry-aware retrieval.
- Only approved, unexpired memories are retrieved into the reasoning pipeline, with bounded prompt context.
- Tenant-scoped lesson candidates reference owned evaluation IDs.
- Lesson candidate and decision records are immutable/append-only.
- Independent reviewer scope is required for lesson approval.
- Runtime promotion of lesson candidates is disabled.
- CI has tests for approval, isolation, scope, evidence ownership, and review boundaries.

## Gap
The system does not yet demonstrate a closed, verified feedback path from a task/conversation outcome to a proposed lesson. A lesson candidate can be manually proposed using evaluation IDs; approved lesson candidates do not become runtime memory. This is a deliberate safety boundary, not a bug to bypass.

## Safe proposed lifecycle
1. **Capture outcome:** store an explicit user outcome/feedback or deterministic evaluation tied to the task/conversation ID and owner/tenant.
2. **Generate suggestion:** create a bounded, non-executable lesson candidate only from that evidence. Candidate is marked pending and never enters prompt memory.
3. **Review:** an authenticated owner/reviewer approves or rejects with rationale; decision is immutable.
4. **Use:** only approved, unexpired user memories are retrieved into reasoning, bounded and labelled reference data. Lesson promotion stays disabled unless a separate, reviewed mapping is introduced.
5. **Measure:** link future evaluations to the candidate/approved memory ID; report whether outcomes improved without claiming causal learning from a single event.
6. **Delete/expire:** retain user control and enforce expiry/deletion; keep no content after deletion except necessary minimal audit, if policy permits.

## Minimum implementation/test gates
- Candidate is tenant/owner isolated and references an existing owned evaluation/outcome.
- No model can approve, promote, or write durable memory directly.
- No candidate is retrieved before explicit approval.
- Prompt injection in candidate text is treated as data, never instructions.
- Candidate generation is bounded, idempotent, and auditable.
- Approval is identity-verified, not a caller-supplied label.
- Tests prove approval/rejection, cross-tenant isolation, duplicate handling, deletion/expiry, and retrieval boundaries.
- No automatic promotion, self-modifying code, deployment, or paid provider calls.

## Next task
Prototype a deterministic, explicit-feedback-to-candidate workflow on an isolated branch. First inspect the exact PR #11 APIs and storage contracts; do not duplicate existing candidate proposal endpoints.