"""Resolve client IPs without trusting caller-controlled forwarding headers.

Only a peer inside an explicitly configured trusted-proxy CIDR may supply
X-Forwarded-For. The chain is evaluated from the nearest hop outwards, stopping
at the first address that is not itself a trusted proxy.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field


IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

MAX_FORWARDED_FOR_LENGTH = 2048
DEFAULT_MAX_FORWARDED_HOPS = 16


def _parse_address(value: object, label: str) -> IPAddress:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 128
        or any(ord(char) < 33 or ord(char) == 127 for char in value)
    ):
        raise ValueError(f"A valid {label} IP address is required.")
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise ValueError(f"A valid {label} IP address is required.") from None

    if isinstance(address, ipaddress.IPv6Address):
        if address.scope_id is not None:
            raise ValueError("Scoped IPv6 client addresses are not supported.")
        if address.ipv4_mapped is not None:
            return address.ipv4_mapped
    return address


@dataclass(frozen=True)
class TrustedProxyClientAddressResolver:
    """Resolve a canonical client IP using an explicit trusted-proxy allowlist.

    The proxy deployment must append its observed peer address to
    X-Forwarded-For. The header is ignored entirely when the immediate peer is
    not trusted. If a trusted peer omits or corrupts the header, resolution
    fails rather than falling back to an ambiguous address.
    """

    trusted_proxy_cidrs: tuple[str, ...] = ()
    max_forwarded_hops: int = DEFAULT_MAX_FORWARDED_HOPS
    _trusted_networks: tuple[IPNetwork, ...] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if isinstance(self.trusted_proxy_cidrs, str):
            raise ValueError("Trusted proxy CIDRs must be a sequence of networks.")
        try:
            configured = tuple(self.trusted_proxy_cidrs)
        except TypeError:
            raise ValueError("Trusted proxy CIDRs must be a sequence of networks.") from None
        if len(configured) > 128:
            raise ValueError("At most 128 trusted proxy CIDRs may be configured.")
        networks: list[IPNetwork] = []
        for value in configured:
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError("Each trusted proxy CIDR must be a valid network.")
            try:
                networks.append(ipaddress.ip_network(value, strict=False))
            except ValueError:
                raise ValueError("Each trusted proxy CIDR must be a valid network.") from None
        if (
            isinstance(self.max_forwarded_hops, bool)
            or not isinstance(self.max_forwarded_hops, int)
            or not 1 <= self.max_forwarded_hops <= 32
        ):
            raise ValueError("Maximum forwarded hops must be between 1 and 32.")
        object.__setattr__(self, "trusted_proxy_cidrs", configured)
        object.__setattr__(self, "_trusted_networks", tuple(networks))

    def _is_trusted_proxy(self, address: IPAddress) -> bool:
        return any(
            address.version == network.version and address in network
            for network in self._trusted_networks
        )

    def resolve(self, remote_addr: str, forwarded_for: str | None = None) -> str:
        """Return a canonical IP string or raise when a trusted chain is invalid."""
        peer = _parse_address(remote_addr, "remote peer")
        if not self._is_trusted_proxy(peer):
            # Never parse or trust a forwarding header supplied by an untrusted peer.
            return peer.compressed

        if (
            not isinstance(forwarded_for, str)
            or not forwarded_for
            or len(forwarded_for) > MAX_FORWARDED_FOR_LENGTH
            or any(ord(char) < 32 or ord(char) == 127 for char in forwarded_for)
        ):
            raise ValueError("A valid trusted X-Forwarded-For chain is required.")

        raw_hops = forwarded_for.split(",")
        if len(raw_hops) > self.max_forwarded_hops:
            raise ValueError("The forwarded client-address chain is too long.")

        hops: list[IPAddress] = []
        for raw_hop in raw_hops:
            token = raw_hop.strip()
            if not token:
                raise ValueError("The forwarded client-address chain is malformed.")
            hops.append(_parse_address(token, "forwarded"))

        # Walk from the immediate trusted peer towards the client. Stop at the
        # first untrusted hop so caller-supplied values further left are ignored.
        candidate = peer
        for hop in reversed(hops):
            if not self._is_trusted_proxy(candidate):
                break
            candidate = hop
        return candidate.compressed
