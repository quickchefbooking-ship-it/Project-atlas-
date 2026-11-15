# Professor cognitive kernel

The cognitive kernel is the deterministic control plane for THE PROFESSOR. It
prepares a bounded task frame before model reasoning, specialist routing,
memory retrieval, or planning.

## Current boundary

- Intake validates and bounds task, context, goal, and constraints.
- Framing distinguishes the requested task from supplied context and records
  missing context/constraints as assumptions rather than inventing facts.
- Ambiguous short requests are held for clarification.
- Drafting remains draft-only. Requests that may create external side effects
  are marked as requiring separate, verified human approval.
- A deterministic review returns quality and safety findings.

## Deliberate limitations

This kernel does not claim human-like understanding, call an LLM, retrieve or
write memory, select capabilities, execute plans, or perform I/O. It is the
first control stage to be composed with the existing conversation, evidence,
learning, planning, and audit modules. Model output must not override these
boundaries. Execution remains separately gated.

## Next composition stages

1. Connect the frame to evidence-aware context retrieval with source provenance.
2. Compose a structured reasoning result and decomposition against the existing
   ProfessorPlan contract.
3. Add a critique/evaluation pass checking goal coverage, constraints, evidence,
   and uncertainty before producing a user-facing response.
4. Persist the stage trace through the tenant-scoped audit path.
