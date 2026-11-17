# Trusted client-address resolution

## Status

A provider- and framework-neutral resolver is implemented with regression
coverage. It is not yet wired into hosted OIDC routes or the persistent login
abuse guard. Public login remains disabled.

## Trust model

- The immediate TCP peer address is authoritative unless it belongs to an
  explicitly configured trusted-proxy CIDR.
- `X-Forwarded-For` is ignored entirely when the immediate peer is not trusted.
- When the immediate peer is trusted, the resolver requires a bounded,
  syntactically valid IP-only forwarding chain.
- The chain is evaluated from right to left. Traversal stops at the first hop
  that is not itself in the trusted-proxy allowlist; values further to the left
  are not trusted.
- IPv4-mapped IPv6 values are normalized to native IPv4. IPv6 values use
  compressed canonical notation. Scoped IPv6 addresses, hostnames, ports,
  malformed chains and excessive hop counts are rejected.

The configured reverse proxy must append the address of the peer it actually
observed. A proxy that replaces or blindly preserves caller-supplied forwarding
headers does not satisfy this trust model.

## Deployment integration gate

Before a public authentication route uses this resolver:

1. Obtain the immediate peer from the ASGI connection, not from a request
   header.
2. Load trusted proxy CIDRs from reviewed deployment configuration.
3. Configure only the actual proxy hops controlled by the deployment.
4. Do not trust all private networks or broad cloud ranges by default.
5. Treat a malformed chain from a trusted proxy as a failed request; do not
   fall back to caller-supplied values.
6. Pass only the resolver's canonical result to the login abuse guard.
7. Add route-level tests for the actual Replit/proxy topology before enabling
   public login.

This component does not configure a proxy, infer Replit's network topology,
apply rate limits, provision secrets, or enable public sign-in.
