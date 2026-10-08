"""Stdlib webhook receiver on 127.0.0.1 that records requests and replays scripted statuses."""

import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Any


@dataclass(frozen=True)
class Received:
    path: str
    headers: dict[str, str]
    body: bytes

    @property
    def json(self) -> dict[str, Any]:
        parsed = json.loads(self.body)
        assert isinstance(parsed, dict)
        return parsed


class WebhookReceiver:
    """Use as a context manager. ``statuses`` are consumed per request; then ``default_status``."""

    def __init__(self, statuses: list[int] | None = None, default_status: int = 200) -> None:
        self._statuses = list(statuses or [])
        self._default = default_status
        self._lock = threading.Lock()
        self.requests: list[Received] = []
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib hook name
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                with receiver._lock:
                    receiver.requests.append(
                        Received(self.path, {k: v for k, v in self.headers.items()}, body)
                    )
                    status = receiver._statuses.pop(0) if receiver._statuses else receiver._default
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return None

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/hook"

    def __enter__(self) -> "WebhookReceiver":
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
