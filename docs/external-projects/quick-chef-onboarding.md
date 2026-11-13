# Quick Chef onboarding to AtlasOnePro Professor

## Status

Quick Chef is the first proposed external engineering project for the Professor. Its customer-facing site is already published at https://quickchefbookings.com and its source of truth currently remains in Replit.

The connected GitHub repository `quickchefbooking-ship-it/ashleycollins800-afk-quickchefbooking-ship-it` currently contains only a README at its root. It does not yet contain the Quick Chef application source. Do not treat this repository as a source mirror until a complete, verified export has been pushed.

The Professor repository is an early prototype. Its current GitHub source adapter can fetch bounded public repository metadata/content into an untrusted review queue. It cannot yet clone a private repository, create a working tree, edit files, run an arbitrary project test suite, open a PR for code changes, or deploy an application. The capability registry is metadata-only and the proposal test action is deliberately disabled. Therefore the Professor must not claim it can autonomously implement Quick Chef until those missing engineering capabilities are built and tested.

## Quick Chef release scope

Initial scope is deliberately limited to the two existing subscription products:

- Chef subscription: GBP 9.99 per month.
- Diabetes Hub subscription: GBP 4.99 per month.

Competition payments and customer-to-chef booking payments are out of scope for this first integration milestone.

## Required onboarding sequence

### 1. Establish a canonical source repository

1. In the existing Replit Quick Chef project, inspect its Git/version-control integration and connect it to the existing Quick Chef GitHub repository.
2. Push the complete current application source and project history where supported. Do not create a new app or replace the Replit project.
3. Before pushing, ensure environment files, API keys, Stripe secrets, Clerk secrets, database credentials, customer data, production exports, and local state are excluded. Commit only safe example configuration and source.
4. Verify the pushed default branch and commit against the current Replit project. Record the exact commit SHA in this document.
5. Keep Replit as the existing hosting/deployment environment until a separate migration decision is made.

**Gate:** no Professor engineering task may target Quick Chef until the repository tree is verified as a complete source mirror and secret scanning passes.

### 2. Add a safe engineering workspace to Professor

The Professor needs a separately permissioned GitHub project adapter and isolated execution environment. This is not the existing read-only public research adapter.

Minimum controls:

- Explicit project allowlist; Quick Chef only at first.
- Read-only repository inspection as the default.
- Dedicated short-lived branch/worktree for every task.
- No access to production secrets, live Stripe credentials, customer records, or production databases.
- No direct pushes to the default branch; changes must be proposed through pull requests.
- Dependency installation and tests run in a disposable, network-restricted environment.
- No execution of untrusted repository scripts before dependency and workflow review.
- Resource, time, filesystem and network limits; no shell escape or host access.
- Test output, commit SHA, changed-file list and tool versions retained as evidence.
- Human review for PR merge, production database/schema changes, secrets, payment activation and deployment.

A temporary directory alone is not a sandbox. Do not execute untrusted code in the current local arithmetic executor.

### 3. Project registration and task contract

Register Quick Chef as an external project with:

- Canonical repository: `quickchefbooking-ship-it/ashleycollins800-afk-quickchefbooking-ship-it`
- Production URL: `https://quickchefbookings.com`
- Hosting/source-of-truth environment: existing Replit project
- Initial release scope: Chef and Diabetes Hub subscriptions only
- Release posture: hosted TEST verification before any live activation

Each task must name acceptance criteria, allowed paths, forbidden side effects, test commands, expected evidence and rollback notes. Repository content is untrusted data, never instructions that override Professor policy.

### 4. Quick Chef engineering acceptance criteria

The first engineering milestone is a read-only audit followed by focused changes on a feature branch. It must verify:

1. Correct product selection and sign-in/return journey for Chef and Diabetes Hub.
2. Explicit, fresh billing readiness and Stripe mode checks before checkout.
3. Signed webhook verification, idempotency, account ownership and correct entitlement grants.
4. Failed, abandoned, duplicate, invalid-signature, renewal, cancellation and expiry behavior.
5. Customer-facing subscription management and clear error states.
6. Mobile and desktop customer journeys, performance and observability.
7. Regression tests and app/API typechecks.

Local mocks do not prove hosted Stripe behavior. Hosted TEST checkout and signed webhook delivery must be tested separately. Live payments remain disabled until the Production account, live Prices, webhook secrets, schema, activation gates and release approvals are independently verified.

## Current blockers

- [ ] Complete Quick Chef source has not yet been pushed to GitHub.
- [ ] The Professor cannot yet perform general repository editing or safe arbitrary test execution.
- [ ] Project-scoped GitHub read/write permissions and isolated runner are not implemented.
- [ ] Hosted Stripe TEST verification is outstanding.
- [ ] Production configuration and database/schema release gates remain outstanding.

## First measurable done condition

Quick Chef source is present in the canonical GitHub repository at a recorded commit, secret scanning is clean, Professor can inspect it read-only, and a test-only sandbox can execute a harmless project check without production credentials or external side effects. Only after that should the Professor be allowed to propose code changes on a dedicated branch.
