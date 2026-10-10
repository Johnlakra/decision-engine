"""SSRF guard for subscriber URLs (FR-42, NFR-05)."""

import pytest

from app.integrations.ssrf import UnsafeUrl, check_url


def resolver_for(*addresses: str):  # type: ignore[no-untyped-def]
    return lambda host: list(addresses)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.0.9",
        "192.168.1.1",
        "169.254.169.254",
        "0.0.0.0",  # noqa: S104
        "::1",
        "fd00::1",
        "fe80::1",
        "224.0.0.1",
        "ff02::1",
        "::ffff:127.0.0.1",
    ],
)
def test_private_targets_refused(address: str) -> None:
    with pytest.raises(UnsafeUrl):
        check_url("https://hook.example.com/x", allow_private=False, resolver=resolver_for(address))


def test_any_private_answer_among_public_refuses() -> None:
    with pytest.raises(UnsafeUrl):
        check_url(
            "https://hook.example.com/x",
            allow_private=False,
            resolver=resolver_for("93.184.216.34", "10.0.0.1"),
        )


def test_public_https_allowed() -> None:
    check_url(
        "https://hook.example.com/x", allow_private=False, resolver=resolver_for("93.184.216.34")
    )


def test_literal_ip_is_checked_without_dns() -> None:
    with pytest.raises(UnsafeUrl):
        check_url("https://169.254.169.254/latest", allow_private=False)


def test_http_refused_unless_allowed() -> None:
    with pytest.raises(UnsafeUrl):
        check_url(
            "http://hook.example.com/x", allow_private=False, resolver=resolver_for("8.8.8.8")
        )


@pytest.mark.parametrize(
    "url", ["ftp://example.com/x", "https:///x", "not a url", "file:///etc/passwd"]
)
def test_bad_scheme_or_host_refused(url: str) -> None:
    with pytest.raises(UnsafeUrl):
        check_url(url, allow_private=True, resolver=resolver_for("8.8.8.8"))


def test_allow_private_permits_loopback_http() -> None:
    check_url("http://127.0.0.1:9000/hook", allow_private=True)


def test_unresolvable_host_refused() -> None:
    def boom(host: str) -> list[str]:
        raise OSError("nxdomain")

    with pytest.raises(UnsafeUrl):
        check_url("https://nope.invalid/x", allow_private=False, resolver=boom)


def test_credentials_in_url_refused() -> None:
    with pytest.raises(UnsafeUrl):
        check_url(
            "https://user:pw@hook.example.com/x",
            allow_private=False,
            resolver=resolver_for("8.8.8.8"),
        )


@pytest.mark.parametrize(
    "address",
    [
        "64:ff9b::a9fe:a9fe",  # NAT64 wrapping 169.254.169.254
        "64:ff9b::7f00:1",  # NAT64 wrapping 127.0.0.1
        "64:ff9b::a00:1",  # NAT64 wrapping 10.0.0.1
        "64:ff9b:1::1",  # local-use NAT64
        "2002:a9fe:a9fe::1",  # 6to4 wrapping 169.254.169.254
        "2002:7f00:1::1",  # 6to4 wrapping 127.0.0.1
        "2002:c0a8:101::1",  # 6to4 wrapping 192.168.1.1
        "fec0::1",  # deprecated site-local
        "fe80::1:2",  # link-local
        "192.0.0.1",  # IETF protocol assignments
        "192.0.0.170",
    ],
)
def test_embedded_and_special_ranges_refused(address: str) -> None:
    """FR-42, NFR-05: NAT64, 6to4, site-local and 192.0.0.0/24 are never public."""
    with pytest.raises(UnsafeUrl):
        check_url("https://hook.example.com/x", allow_private=False, resolver=resolver_for(address))


@pytest.mark.parametrize("address", ["64:ff9b::5db8:d822", "2002:5db8:d822::1"])
def test_embedded_public_ipv4_is_still_allowed(address: str) -> None:
    """FR-42: NAT64/6to4 wrapping a public IPv4 (93.184.216.34) passes the same rules."""
    check_url("https://hook.example.com/x", allow_private=False, resolver=resolver_for(address))


def test_allow_private_still_skips_the_guard() -> None:
    """FR-42: allow_private behaviour unchanged."""
    assert check_url("http://127.0.0.1:9/x", allow_private=True) == []
