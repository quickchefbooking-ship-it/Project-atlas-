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
- The authenticated Professor chat endpoint now routes through this cognitive pipeline and includes bounded prior conversation context. Held answers are not represented as completed external actions.

## Important limitations

The critique uses lexical coverage as a warning signal, not semantic proof. A
future model-based critic may add semantic review, but must not override
application-owned policy, evidence provenance, approval or execution boundaries.
This module does not claim human-like cognition and does not execute tools.

## Next composition stages

1. Connect the validated decomposition to the existing model-provider adapter and capability registry, keeping capability metadata application-owned.
2. Add an end-to-end conversation pipeline that records intake, evidence, plan proposal, critique and final response in the tenant-scoped reasoning trace.
3. Add adversarial tests for prompt injection in evidence, provider output and specialist handoffs.
4. Keep all external actions in draft/approval states until action-bound authorisation is independently verified.
