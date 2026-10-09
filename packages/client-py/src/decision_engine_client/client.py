"""Thin hand-written wrapper over the generated client: auth, timeouts, retries (FR-96)."""

import time
from collections.abc import Callable
from typing import Any, TypeVar
from uuid import UUID

import httpx

from ._generated import AuthenticatedClient
from ._generated.api.decide import decide_sync
from ._generated.api.items import (
    create_item,
    create_items_bulk,
    decide_item,
    get_item,
    list_items,
)
from ._generated.models import (
    BulkOut,
    CreateItemsBulkPayload,
    DecideIn,
    DecideOut,
    DecisionIn,
    DecisionItemOut,
    DecisionResult,
    IngestItemIn,
    IngestResult,
    ItemPage,
)

T = TypeVar("T")
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_BACKOFF_S = 30.0
BASE_BACKOFF_S = 0.5


def _delay(response: httpx.Response | None, attempt: int) -> float:
    """Honour a numeric Retry-After, else exponential backoff (0.5s, 1s, 2s ...)."""
    if response is not None:
        raw = response.headers.get("Retry-After")
        if raw is not None and raw.strip().isdigit():
            return min(float(raw), MAX_BACKOFF_S)
    return min(BASE_BACKOFF_S * (2**attempt), MAX_BACKOFF_S)


class RetryTransport(httpx.BaseTransport):
    """Retry 429/5xx responses and connection errors. Safe because ingest is idempotent."""

    def __init__(
        self,
        retries: int = 3,
        *,
        inner: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._retries = retries
        self._inner = inner or httpx.HTTPTransport()
        self._sleep = sleep

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        for attempt in range(self._retries + 1):
            is_last = attempt == self._retries
            try:
                response = self._inner.handle_request(request)
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError):
                if is_last:
                    raise
                self._sleep(_delay(None, attempt))
                continue
            if response.status_code not in RETRY_STATUSES or is_last:
                return response
            response.close()
            self._sleep(_delay(response, attempt))
        raise AssertionError("unreachable")  # pragma: no cover

    def close(self) -> None:
        self._inner.close()


class DecisionEngine:
    """Convenience facade. Use ``.raw`` for the full generated client."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 10,
        retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        retrying = RetryTransport(retries, inner=transport, sleep=sleep)
        self.raw = AuthenticatedClient(
            base_url=base_url.rstrip("/"),
            token=api_key,
            timeout=httpx.Timeout(timeout),
            raise_on_unexpected_status=True,
            httpx_args={"transport": retrying},
        )

    def create_item(self, body: IngestItemIn) -> IngestResult:
        return _required(create_item.sync(client=self.raw, body=body))

    def create_items_bulk(self, body: CreateItemsBulkPayload) -> BulkOut:
        return _required(create_items_bulk.sync(client=self.raw, body=body))

    def get_item(self, item_id: UUID) -> DecisionItemOut:
        return _required(get_item.sync(item_id, client=self.raw))

    def list_items(self, **filters: Any) -> ItemPage:
        """Filters: status, niche, source, q, cursor, limit."""
        return _required(list_items.sync(client=self.raw, **filters))

    def decide_item(self, item_id: UUID, body: DecisionIn) -> DecisionResult:
        return _required(decide_item.sync(item_id, client=self.raw, body=body))

    def decide(self, body: DecideIn) -> DecideOut:
        return _required(decide_sync.sync(client=self.raw, body=body))


def _required(parsed: T | None) -> T:
    if parsed is None:
        raise RuntimeError("empty response body")
    return parsed
