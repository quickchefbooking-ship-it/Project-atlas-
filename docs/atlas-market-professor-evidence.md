# Professor and Atlas Market Intelligence Evidence Contract

## Status
This draft adds an evidence adapter to the GitHub market-data branch. It does not establish a Replit runtime integration, real market feed, trading capability or deployment.

## Evidence flow
1. The deterministic synthetic market read model supplies canonical instrument identity, venue, interval, timestamps and quality labels.
2. The Professor adapter accepts bounded JSON-compatible evidence and normalises aware timestamps to UTC.
3. It hashes a canonical evidence envelope and stores it using the existing Atlas LearningMemory/storage subsystem.
4. Newly recorded lessons are always unvalidated. Recording a passing test does not automatically promote a lesson into trusted guidance.
5. Only the existing owner-validated lesson retrieval path can return market lessons to Professor.
6. Returned material is advisory and non-executable.

## Outcomes
The adapter distinguishes verified, failed, partial and uncertain. Verified means only that the stated validation procedure passed within its claim scope. Synthetic fixture evidence explicitly says it is not a real market observation.

## Boundaries
- No duplicate learning store or database schema.
- No broker or provider connection, account access, order routes, paper order creation or live execution.
- No automatic lesson validation, strategy mutation, risk-limit changes or permission changes.
- No HTTP endpoint added here; authenticated route integration is a separate reviewed slice.
- No Replit, secrets, production database, payment or deployment changes.

## Verification
The associated tests check evidence persistence, provenance, outcome distinctions, timestamp validation, bounded size, and owner-validation gating. Exact-head CI must pass before this draft can be considered verified.
