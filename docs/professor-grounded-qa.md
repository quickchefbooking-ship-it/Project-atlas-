# Professor grounded report questions

The first tenant-facing question-and-answer slice is deliberately bounded to completed
`professor_evidence_report` results.

## Endpoint

`POST /professor/tenant/plans/{plan_id}/ask`

Authentication uses the verified OIDC principal. The caller needs `steps:read`. The plan ID is only a selector; tenant identity
and permissions are derived server-side. The request accepts only a
`question` string (1–1000 characters); unexpected fields are rejected.

## Behaviour

- Reads the plan through the tenant-scoped plan repository.
- Reads succeeded step results through the tenant-scoped step repository.
- Answers only from one completed Professor evidence report in that plan.
- Returns source IDs, claim IDs and recorded report sections where relevant.
- Returns an explicit insufficient-context answer when the report cannot answer.
- Labels the mode `deterministic_report_grounded`.
- Does not call an LLM, access the web, invoke capabilities, execute a plan,
  change evidence reviews, or persist conversation history.

The deterministic responder recognises summary, findings, challenges,
disagreements, evidence gaps and source-register questions. Other questions
receive lexical claim matching only; unmatched questions are not guessed.

## Trust boundary

Report text and source metadata are untrusted data. They are returned as data
and are never interpreted as instructions. Annotation labels are not
independent verification; the report's limitations remain part of the answer.

The endpoint is implemented in the tenant evidence-review router and is included in the authenticated report interface. This is not the general conversational reasoning provider. The provider-neutral
conversation contract remains separate and fail-closed until an approved model
provider is configured. The report page uses the same short-lived OIDC token
and plan ID to ask questions against the already loaded report.

## Tests

Unit tests cover section retrieval, source provenance, lexical matching,
unknown questions, size limits and instruction-like report text. HTTP tests
cover successful tenant-scoped answers, cross-tenant denial, missing scope and
strict request validation.
