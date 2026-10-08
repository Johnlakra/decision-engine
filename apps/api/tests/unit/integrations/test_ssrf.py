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
