"""Tiny local webhook receiver that verifies the ``t=<unix>,v1=<hex>`` signature (L2, FR-42).

Usage: ``python -m scripts.webhook_receiver --port 9099 --secret s3cr3t`` (or set
``DE_WEBHOOK_SECRET``). Prints ``signature OK <event> <id>`` for each good delivery and answers
401 for a bad one, so the API's retry path is visible. Dev tool: it only prints event ids.
"""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from app.security.hmac import InvalidSignature, verify

SIGNATURE_HEADER = "X-DE-Signature"
MAX_BODY_BYTES = 1_000_000
DEFAULT_PORT = 9099


def check_delivery(secret: bytes, body: bytes, signature: str) -> str:
    """Return the success line, or raise InvalidSignature."""
    verify(secret, body, signature)
    try:
        envelope = json.loads(body)
    except ValueError as error:
        raise InvalidSignature("body is not JSON") from error
    if not isinstance(envelope, dict):
        raise InvalidSignature("body is not a JSON object")
    return f"signature OK {envelope.get('event', '?')} {envelope.get('id', '?')}"


def build_server(host: str, port: int, secret: bytes) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib hook name
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_BODY_BYTES:
                self._reply(413, "body too large")
                return
            body = self.rfile.read(length)
            try:
                line = check_delivery(secret, body, self.headers.get(SIGNATURE_HEADER, ""))
            except InvalidSignature as error:
                print(f"signature INVALID: {error.reason}", flush=True)  # noqa: T201
                self._reply(401, "invalid signature")
                return
            print(line, flush=True)  # noqa: T201 - CLI output
            self._reply(200, "ok")

        def _reply(self, status: int, message: str) -> None:
            payload = message.encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return None

    return ThreadingHTTPServer((host, port), Handler)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify signed decision-engine webhooks.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="0.0.0.0", help="0.0.0.0 so Docker can reach the host")  # noqa: S104
    parser.add_argument("--secret", default=os.environ.get("DE_WEBHOOK_SECRET", ""))
    args = parser.parse_args(argv)
    if not args.secret:
        print("webhook_receiver: pass --secret or set DE_WEBHOOK_SECRET", file=sys.stderr)  # noqa: T201
        return 2
    server = build_server(args.host, args.port, args.secret.encode())
    print(f"listening on {args.host}:{server.server_address[1]}", flush=True)  # noqa: T201
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
