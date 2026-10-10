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


_DENIED_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "192.0.0.0/24",  # IETF protocol assignments (is_global has exceptions inside it)
        "fec0::/10",  # deprecated site-local
        "64:ff9b:1::/48",  # local-use NAT64
    )
)
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_SIXTO4 = ipaddress.ip_network("2002::/16")


def _embedded_ipv4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """IPv4 wrapped by an IPv4-mapped, NAT64 or 6to4 address, else None."""
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    if ip in _NAT64:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    if ip in _SIXTO4:
        return ipaddress.IPv4Address((int(ip) >> 80) & 0xFFFFFFFF)
    return None


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = _embedded_ipv4(ip)
        if embedded is not None:
            return _is_public(str(embedded))
    if any(ip in network for network in _DENIED_NETWORKS if network.version == ip.version):
        return False
    return ip.is_global and not ip.is_multicast


def check_url(url: str, *, allow_private: bool, resolver: Resolver | None = None) -> list[str]:
    """Raise UnsafeUrl unless ``url`` is https (or allowed) and resolves only to public IPs.

    Returns the vetted addresses so the caller can pin its connection to them (empty when
    ``allow_private`` skips resolution).
    """
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
        return []
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
    return addresses
