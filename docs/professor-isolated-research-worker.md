# Professor isolated research worker — architecture decision and release gate

**Status: design and application-layer destination guard only. No worker isolation is implemented or enabled.**

## Decision

The network-capable Crossref capability must not execute inside the API process once the worker boundary is introduced. The API process remains responsible for identity, tenant/scope checks, plan readiness, the global execution gate, and the durable audit reservation. A separately launched, short-lived worker performs only the fixed public Crossref lookup. The parent validates the returned JSON against the registered capability output schema before persisting it.

Do not add further network-capable or credential-bearing handlers until the worker has passed the acceptance gates in this document.

## Current boundary (important)

The current Crossref adapter is still called in-process. It currently has:
- a fixed HTTPS Crossref API URL;
- GET-only request construction;
- an eight-second transport timeout;
- a 1 MB response ceiling;
- redirect rejection;
- bounded query and result counts;
- a newly added application-layer origin/path allowlist in `_get_json`.

The allowlist permits only:
- `https://api.crossref.org/works`;
- `https://api.github.com/repos/{owner}/{repository}`;
- `https://huggingface.co/api/models/{resource}`;
- `https://huggingface.co/api/datasets/{resource}`.

This is not a network firewall. It does not constrain DNS resolution, process privileges, outbound sockets elsewhere in the process, or the operating system's network routes. It does not forcibly terminate a stuck handler. The current Crossref execution route is therefore a prototype, not a production isolation boundary.

## Parent/worker contract

The parent must:
1. Authenticate the user and resolve tenant membership and scopes.
2. Check the global execution gate and exact capability version.
3. Validate the plan step and bounded input.
4. Commit the append-only execution audit reservation before creating or starting a worker.
5. Construct a server-owned, versioned envelope containing only the operation name, bounded query, result limit, request/trace IDs, and input digest. Never accept an executable path, module name, URL, host, credential, or environment variable from the task.
6. Start the one fixed worker entry point without a shell, using a minimal allowlisted environment and a private per-invocation working directory.
7. Enforce a hard wall-clock deadline and output byte limit outside the worker.
8. Validate worker output against the registered output schema in the parent.
9. Append the terminal audit event and persist the step result.

The worker must:
- expose exactly one fixed operation: public Crossref bibliographic search;
- accept one bounded JSON request from the parent;
- construct the Crossref URL internally from validated fields;
- use HTTPS GET only, certificate verification, no redirects and a fixed destination policy;
- reject private, loopback, link-local, multicast and metadata-service destinations at the network boundary;
- have no application credentials, inherited API keys, database paths, home-directory access or other arm credentials;
- return one bounded JSON response and no executable or filesystem artifact;
- never decide tenant permissions, approvals or plan state.

The parent must not trust worker output, error text, timestamps or claims of policy compliance. It revalidates all output.

## Isolation requirements

A child process alone is not a security sandbox. The release worker must run with operating-system enforcement:
- a dedicated unprivileged identity;
- isolated process/container namespace;
- read-only root filesystem and bounded scratch storage;
- no host socket, host filesystem mounts or inherited secrets;
- CPU, memory, process-count, file-size, response-size and wall-clock limits;
- hard process-tree termination on timeout or cancellation;
- deny-by-default network egress through an allowlisting proxy or enforceable firewall policy;
- destination/IP validation that resists DNS rebinding and redirects;
- restrictive syscall/capability profile where supported;
- auditable worker image/runtime version and dependency inventory.

Linux deployment should use an OCI/container boundary with non-root execution, dropped capabilities, no-new-privileges, read-only filesystem, resource cgroups and restricted egress. Windows deployment needs an equivalent reviewed boundary (for example, a restricted worker identity, Job Object resource/termination controls, and enforced outbound firewall/proxy policy). macOS development may use a supported container runtime, but must not be treated as production isolation by itself.

No platform is selected yet. Do not hard-code Docker, Windows-specific APIs, or a hosted provider into the core Professor brain. Keep the worker-launch contract behind an adapter so the central backend can run it on an approved host later. A phone or tablet is a client, not the worker host.

## Failure and recovery semantics

- Audit reservation failure: do not spawn the worker.
- Worker unavailable or policy missing: do not fall back to in-process network execution.
- Timeout or forced termination after dispatch: mark the attempt as unknown/recovery-required; do not automatically replay.
- Malformed, oversized or schema-invalid output: reject it, record a bounded failure event and do not pass it to another capability.
- Network denial, unexpected destination, redirect or TLS failure: fail closed.
- Kill switch disabled: reject before worker creation.
- Emergency stop: future owner control must stop new dispatches and signal in-flight workers; hard termination belongs to the worker supervisor, not browser JavaScript.

## Acceptance tests before enabling the worker

1. Assert no worker starts when identity, tenant, scope, plan, capability version, audit reservation or global kill switch checks fail.
2. Assert the worker receives no application secrets or database path.
3. Assert no shell is used and no task-supplied executable/URL/host is accepted.
4. Assert only the Crossref operation and approved host/path can be invoked.
5. Assert redirect, HTTP, alternate port, userinfo, private/loopback/link-local/metadata IP and DNS-rebinding attempts are denied at the egress boundary.
6. Assert response bytes, output bytes, CPU, memory, process count and wall-clock time are bounded.
7. Assert a deliberately unresponsive worker is forcibly terminated, including descendants, on supported operating systems.
8. Assert timeout after dispatch leaves a durable unknown/recovery-required record and is never automatically replayed.
9. Assert valid worker output is schema-validated by the parent; invalid/oversized output is rejected.
10. Assert kill switch and future owner emergency-stop controls prevent new dispatch and terminate active workers as designed.
11. Run integration tests inside the actual sandbox image/runtime, not only mocked unit tests.
12. Record image digest, OS/runtime version, policy version and exact CI evidence.

## Explicit non-claims

Until every acceptance test passes on the selected deployment host:
- Crossref is still in-process;
- application-layer URL validation is not network egress isolation;
- an eight-second HTTP timeout is not hard process termination;
- no claim of production-grade worker isolation or autonomous safe execution is permitted.
