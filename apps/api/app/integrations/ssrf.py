"""SSRF guard for subscriber URLs (FR-42, NFR-05).

Checked at subscribe time and again at send time. DNS is resolved here; every
answer must be public, otherwise the URL is refused.
"""

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

Resolver = Callable[[str], list[str]]


class UnsafeUrl(ValueError):  # noqa: N818 - public contract name
    """The URL is not an acceptable webhook target."""


def resolve_host(host: str) -> list[str]:
    """Blocking DNS lookup returning every address for ``host``."""
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return [str(info[4][0]) for info in infos]


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def check_url(url: str, *, allow_private: bool, resolver: Resolver | None = None) -> None:
    """Raise UnsafeUrl unless ``url`` is https (or allowed) and resolves only to public IPs."""
    try:
        parts = urlsplit(url)
        host = parts.hostname
        parts.port  # noqa: B018 - validates the port
    except ValueError as exc:
        raise UnsafeUrl("malformed URL") from exc
    if parts.scheme not in ("http", "https") or not host:
        raise UnsafeUrl("URL must be http(s) with a host")
    if parts.username or parts.password:
        raise UnsafeUrl("credentials in URL are not allowed")
    if allow_private:
        return
    if parts.scheme != "https":
        raise UnsafeUrl("URL must use https")
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            addresses = (resolver or resolve_host)(host)
        except OSError as exc:
            raise UnsafeUrl("host does not resolve") from exc
    if not addresses:
        raise UnsafeUrl("host does not resolve")
    if not all(_is_public(address) for address in addresses):
        raise UnsafeUrl("host resolves to a non-public address")
