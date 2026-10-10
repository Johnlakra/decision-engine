"""Request-size limit: 413 problem+json by Content-Length or by counting streamed bytes (NFR-05)."""

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.core.errors import PROBLEM_JSON

BULK_PATH_SUFFIX = "/items/bulk"


def limit_for(path: str) -> int:
    settings = get_settings()
    if path.endswith(BULK_PATH_SUFFIX):
        return settings.max_bulk_request_bytes
    return settings.max_request_bytes


async def _send_413(scope: Scope, send: Send, limit: int) -> None:
    body = json.dumps(
        {
            "type": "about:blank",
            "title": "Payload Too Large",
            "status": 413,
            "detail": f"Request body exceeds {limit} bytes",
            "instance": scope["path"],
        }
    ).encode()
    headers = [
        (b"content-type", PROBLEM_JSON.encode()),
        (b"content-length", str(len(body)).encode()),
        (b"connection", b"close"),
    ]
    await send({"type": "http.response.start", "status": 413, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class BodyLimitMiddleware:
    """Pure ASGI so the body is never buffered beyond the limit."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = limit_for(scope["path"])
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _send_413(scope, send, limit)
            return

        received = 0
        started = False
        rejected = False

        async def counting_receive() -> Message:
            nonlocal received, rejected
            message = await receive()
            if rejected or message["type"] != "http.request":
                return message
            received += len(message.get("body", b""))
            if received > limit and not started:
                # Reply now: frameworks swallow exceptions raised while parsing the body.
                rejected = True
                await _send_413(scope, send, limit)
                return {"type": "http.disconnect"}
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if rejected:  # the 413 is already on the wire; drop the app's follow-up
                return
            started = started or message["type"] == "http.response.start"
            await send(message)

        await self.app(scope, counting_receive, tracking_send)
