# Professor Brain-First Roadmap — 2026-11-23

## Decision
The central Professor brain is the primary delivery priority. QuickChef is being prepared as a future arm in parallel, but integration does not proceed into live data or write operations until the brain's core reliability gates are demonstrated.

## Brain gates (in order)
### Gate 1 — Reliable reasoning and task execution
- Run complete integration tests against a coherent candidate.
- Verify planning, critique, clarification, bounded execution and safe refusal/approval gates.
- Record exact CI evidence and unresolved runtime limitations.

### Gate 2 — Durable memory
- Explicit user-approved memory lifecycle.
- Tenant/owner isolation, expiry, correction/supersession and provenance.
- No automatic promotion from model-generated claims.

### Gate 3 — Retrieval
- Expand synthetic benchmark: paraphrases, distractors, ambiguity, no-answer cases, stale/conflicting items, multilingual probes.
- Report per-query failures and Recall@K, Precision@K, MRR with denominators.
- Add provenance/freshness and retrieval rationale to result contract.
- Do not describe lexical retrieval as semantic understanding.

### Gate 4 — Evaluation and learning
- Establish baseline before lesson use.
- Attribute which lesson was retrieved and applied.
- Compare matched tasks with baseline vs lesson-enabled conditions.
- Track regressions and confidence/sample size.
- Promote only validated, bounded lessons; maintain quarantine/supersession/rollback.

### Gate 5 — Visible observability
A future dashboard should show truthful states:
- experience recorded;
- lesson candidate created;
- pending validation;
- approved memory available;
- memory retrieved/applied (with trace reference);
- evaluation completed;
- measured improvement (only when comparable evidence exists).
Use amber for blocked/incomplete, green only for verified evidence, grey for not measured. Avoid fake activity indicators.

## QuickChef parallel preparation — frozen at architecture/contract stage
- Keep product/database/auth separate.
- Define read-only API adapter contract and mock tests.
- No production credentials, sync, writes, bookings, payments or live data until brain gates and security review permit.
- Once Gate 1–4 pass, pilot one read-only query with least privilege and provenance.

## Current status
- Architecture documents created in PR #87.
- CI is running for the PR at the last observed checkpoint.
- This roadmap is a decision/acceptance document, not a claim that the gates are complete.
