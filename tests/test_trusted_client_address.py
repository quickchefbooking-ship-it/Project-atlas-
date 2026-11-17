import pytest

from atlas_engine.trusted_client_address import (
    MAX_FORWARDED_FOR_LENGTH,
    TrustedProxyClientAddressResolver,
)


def test_untrusted_peer_cannot_override_its_address_with_forwarded_header():
    resolver = TrustedProxyClientAddressResolver(("10.0.0.0/8",))

    assert resolver.resolve(
        "198.51.100.24",
        "203.0.113.99, not-an-ip",
    ) == "198.51.100.24"


def test_trusted_proxy_can_supply_one_client_address():
    resolver = TrustedProxyClientAddressResolver(("10.0.0.0/8",))

    assert resolver.resolve("10.0.0.12", "203.0.113.24") == "203.0.113.24"


def test_trusted_proxy_chain_walks_right_to_left():
    resolver = TrustedProxyClientAddressResolver(("10.0.0.0/8",))

    assert resolver.resolve(
        "10.0.0.2",
        "203.0.113.24, 10.0.0.1",
    ) == "203.0.113.24"


def test_untrusted_values_to_left_of_nearest_untrusted_hop_are_ignored():
    resolver = TrustedProxyClientAddressResolver(("10.0.0.0/8",))

    # The first value could have been supplied by the client. The trusted
    # proxies append their observed peer addresses, so the nearest untrusted
    # hop is the authoritative client address.
    assert resolver.resolve(
        "10.0.0.2",
        "192.0.2.99, 203.0.113.24, 10.0.0.1",
    ) == "203.0.113.24"


def test_chain_stops_at_first_untrusted_proxy_hop():
    resolver = TrustedProxyClientAddressResolver(("10.0.0.0/8",))

    assert resolver.resolve(
        "10.0.0.2",
        "192.0.2.99, 203.0.113.24, 192.0.2.1",
    ) == "192.0.2.1"


def test_trusted_peer_without_forwarded_header_fails_closed():
    resolver = TrustedProxyClientAddressResolver(("10.0.0.0/8",))

    with pytest.raises(ValueError, match="trusted X-Forwarded-For"):
        resolver.resolve("10.0.0.12")


@pytest.mark.parametrize(
    "header",
    [
        "",
        ",",
        "203.0.113.1,,10.0.0.1",
        "203.0.113.1, not-an-ip",
        "203.0.113.1\r\nX-Injected: yes",
        "203.0.113.1:443",
    ],
)
def test_malformed_forwarded_chain_is_rejected(header):
    resolver = TrustedProxyClientAddressResolver(("10.0.0.0/8",))

    with pytest.raises(ValueError):
        resolver.resolve("10.0.0.12", header)


def test_forwarded_chain_length_is_bounded():
    resolver = TrustedProxyClientAddressResolver(
        ("10.0.0.0/8",),
        max_forwarded_hops=2,
    )

    with pytest.raises(ValueError, match="too long"):
        resolver.resolve("10.0.0.12", "203.0.113.1, 10.0.0.1, 10.0.0.2")


def test_forwarded_header_length_is_bounded():
    resolver = TrustedProxyClientAddressResolver(("10.0.0.0/8",))

    with pytest.raises(ValueError, match="trusted X-Forwarded-For"):
        resolver.resolve("10.0.0.12", "1" * (MAX_FORWARDED_FOR_LENGTH + 1))


def test_ipv4_mapped_ipv6_is_canonicalized_to_native_ipv4():
    resolver = TrustedProxyClientAddressResolver(("10.0.0.0/8",))

    assert resolver.resolve("::ffff:10.0.0.12", "::ffff:203.0.113.24") == "203.0.113.24"


def test_ipv6_is_returned_in_compressed_canonical_form():
    resolver = TrustedProxyClientAddressResolver(("2001:db8:ffff::/48",))

    assert resolver.resolve(
        "2001:0db8:ffff:0000:0000:0000:0000:0002",
        "2001:0db8:0000:0000:0000:0000:0000:0024",
    ) == "2001:db8::24"


def test_invalid_remote_address_is_rejected():
    resolver = TrustedProxyClientAddressResolver()

    with pytest.raises(ValueError, match="remote peer IP"):
        resolver.resolve("unknown-host", "203.0.113.24")


@pytest.mark.parametrize(
    "cidrs",
    [
        "10.0.0.0/8",
        ("not-a-network",),
        ("10.0.0.0/8", " 192.0.2.0/24"),
    ],
)
def test_invalid_trusted_proxy_configuration_is_rejected(cidrs):
    with pytest.raises(ValueError):
        TrustedProxyClientAddressResolver(cidrs)


@pytest.mark.parametrize("max_hops", [0, -1, 33, True, 1.5])
def test_invalid_maximum_forwarded_hops_is_rejected(max_hops):
    with pytest.raises(ValueError, match="between 1 and 32"):
        TrustedProxyClientAddressResolver(
            ("10.0.0.0/8",),
            max_forwarded_hops=max_hops,
        )


def test_empty_trusted_proxy_allowlist_never_trusts_forwarding_header():
    resolver = TrustedProxyClientAddressResolver()

    assert resolver.resolve("10.0.0.12", "203.0.113.24") == "10.0.0.12"
