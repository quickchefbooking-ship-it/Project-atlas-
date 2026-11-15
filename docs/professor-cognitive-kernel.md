# Professor cognitive kernel

The cognitive kernel is the deterministic control plane for THE PROFESSOR.

## Implemented stages

- Bounded intake validates task, context, goal and constraints.
- Ambiguous short requests pause for clarification.
- Missing context and constraints are recorded as assumptions, not invented.
- Action boundaries distinguish information, drafts and externally consequential actions.
- Evidence-aware preparation retrieves only approved, read-only public/curated sources and preserves provenance. Retrieved excerpts are explicitly untrusted data.
- Structured decomposition validates step IDs, dependencies and cycles. It is a proposal only; execution is always disabled.
- Deterministic critique checks visible goal coverage, declared constraints, evidence-document citations and approval boundaries before delivery.
- The two-pass reasoning pipeline asks the explicitly configured provider for a bounded JSON decomposition, validates its structure, then requests an answer and applies the critique gate.
- The authenticated Professor chat endpoint routes through this cognitive pipeline and includes bounded prior conversation context.
- Tenant-scoped audit records include bounded decision metadata and hash-chain verification.
- **Working memory** is bounded recent conversation history. It is not automatically treated as durable user knowledge.
- **Durable memory foundation** is separate: records begin as pending proposals, require an explicit approval decision, are tenant- and owner-scoped, expire after a bounded retention period, and are retrieved only while approved and unexpired. Rejected or pending records are never retrieved.

## Memory boundaries

- Models cannot write or promote durable memory directly.
- A memory proposal is created through an application-controlled repository method and approved using the separate `memory:approve` scope.
- Retention defaults to 90 days and is bounded to 1–3,650 days. Expired records are excluded from retrieval; physical expiry cleanup remains a later maintenance task.
- Owners can explicitly delete stored content. Associated decision details are deleted with it; there is no hidden content archive.
- Retrieval is a simple bounded lexical baseline, not semantic memory. The live chat retrieves at most five approved, unexpired memories only when the verified principal has the `memory:read` scope; otherwise it retrieves none. Memory is clearly labelled as reference data, never instructions, in both reasoning passes.
- No raw hidden chain-of-thought is stored as memory or audit data.
- Verified API routes now support proposal, explicit approval/rejection, bounded retrieval, listing and deletion. They are included in the app and use the separate `memory:propose`, `memory:approve`, `memory:read` and `memory:delete` scopes. A dedicated user-facing review interface and hosted sign-in still need to be completed.

## Important limitations

The critique uses lexical coverage as a warning signal, not semantic proof. This module does not claim human-like cognition and does not execute tools. Memory retrieval is deterministic lexical matching, not a semantic memory system.

## Next composition stages

1. Add authenticated API routes and a review interface for memory proposals, approvals, retrieval and deletion.
2. Integrate approved memory retrieval into reasoning preparation without mixing it with untrusted external evidence.
3. Add expiry cleanup and adversarial tests for memory poisoning and prompt injection.
4. Keep all external actions in draft/approval states until action-bound authorisation is independently verified.
