"""Connection pinning for webhook delivery (NFR-05, FR-42).

The SSRF check resolves the subscriber host once. ``PinnedBackend`` makes the TCP connect
use those vetted addresses instead of resolving again, closing the DNS-rebinding window.
The URL, ``Host`` header, SNI and certificate hostname check keep the original hostname,
because only the address handed to ``connect_tcp`` changes.
"""

from collections.abc import Iterable

import httpcore
import httpx

SocketOption = (
    tuple[int, int, int] | tuple[int, int, bytes | bytearray] | tuple[int, int, None, int]
)


class PinnedBackend(httpcore.AsyncNetworkBackend):
    """Connects ``hostname`` to the given vetted addresses, in order; refuses other hosts."""

    def __init__(
        self,
        hostname: str,
        addresses: Iterable[str],
        *,
        inner: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self._hostname = hostname.lower()
        self._addresses = tuple(addresses)
        self._inner = inner or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - signature fixed by httpcore
        local_address: str | None = None,
        socket_options: Iterable[SocketOption] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        if host.lower() != self._hostname or not self._addresses:
            raise httpcore.ConnectError(f"connection to {host} is not pinned")
        last_error: Exception | None = None
        for address in self._addresses:
            try:
                return await self._inner.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        raise last_error or httpcore.ConnectError("no vetted address")

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 - signature fixed by httpcore
        socket_options: Iterable[SocketOption] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def pinned_transport(
    hostname: str,
    addresses: Iterable[str],
    *,
    network_backend: httpcore.AsyncNetworkBackend | None = None,
) -> httpx.AsyncHTTPTransport:
    """An httpx transport whose connection pool dials only the vetted addresses."""
    transport = httpx.AsyncHTTPTransport(trust_env=False)
    pool = transport._pool  # noqa: SLF001 - httpx exposes no network_backend option
    transport._pool = httpcore.AsyncConnectionPool(  # noqa: SLF001
        ssl_context=pool._ssl_context,  # noqa: SLF001
        max_connections=pool._max_connections,  # noqa: SLF001
        max_keepalive_connections=pool._max_keepalive_connections,  # noqa: SLF001
        keepalive_expiry=pool._keepalive_expiry,  # noqa: SLF001
        http1=pool._http1,  # noqa: SLF001
        http2=pool._http2,  # noqa: SLF001
        network_backend=PinnedBackend(hostname, addresses, inner=network_backend),
    )
    return transport
