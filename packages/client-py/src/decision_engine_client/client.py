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
IDEMPOTENT_POST_PATHS = frozenset({"/v1/items", "/v1/items/bulk"})
DECIDE_MIN_TIMEOUT_S = 35.0  # server decide_timeout_seconds is 30
MAX_BACKOFF_S = 30.0
BASE_BACKOFF_S = 0.5


def _delay(response: httpx.Response | None, attempt: int) -> float:
    """Honour a numeric Retry-After, else exponential backoff (0.5s, 1s, 2s ...)."""
    if response is not None:
        raw = response.headers.get("Retry-After")
        if raw is not None and raw.strip().isdigit():
            return min(float(raw), MAX_BACKOFF_S)
    return min(BASE_BACKOFF_S * (2**attempt), MAX_BACKOFF_S)


def _is_item_decision(path: str) -> bool:
    parts = path.strip("/").split("/")
    return len(parts) == 4 and parts[:2] == ["v1", "items"] and parts[3] == "decision"


def _retries_on_failure(method: str, path: str) -> bool:
    """Allow-list of calls safe to repeat after a 5xx or timeout.

    GET is read-only; ingest is idempotent on source+source_ref. Everything else
    (decide, decisions, subscriptions) may have side effects or be slow by design.
    """
    if method == "GET":
        return True
    return method == "POST" and path.rstrip("/") in IDEMPOTENT_POST_PATHS


def _has_retry_after(response: httpx.Response) -> bool:
    return response.headers.get("Retry-After", "").strip().isdigit()


class RetryTransport(httpx.BaseTransport):
    """Retry per a method+path allow-list (FR-111).

    Allow-listed calls retry on 429, 5xx, connect errors, read timeouts. Every other call
    retries only a 429 that carries ``Retry-After`` (the request was rejected, not run).
    """

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

    def _should_retry(self, request: httpx.Request, response: httpx.Response) -> bool:
        if response.status_code == 429 and _has_retry_after(response):
            return True
        if not _retries_on_failure(request.method.upper(), request.url.path):
            return False
        return response.status_code in RETRY_STATUSES

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        may_retry_failures = _retries_on_failure(request.method.upper(), request.url.path)
        for attempt in range(self._retries + 1):
            is_last = attempt == self._retries
            try:
                response = self._inner.handle_request(request)
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError):
                if is_last or not may_retry_failures:
                    raise
                self._sleep(_delay(None, attempt))
                continue
            if is_last or not self._should_retry(request, response):
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
        self.decide_timeout = max(timeout, DECIDE_MIN_TIMEOUT_S)
        self.raw = self._build(base_url, api_key, timeout, retrying)
        self._decide_client = self._build(base_url, api_key, self.decide_timeout, retrying)

    @staticmethod
    def _build(
        base_url: str, api_key: str, timeout: float, transport: httpx.BaseTransport
    ) -> AuthenticatedClient:
        return AuthenticatedClient(
            base_url=base_url.rstrip("/"),
            token=api_key,
            timeout=httpx.Timeout(timeout),
            raise_on_unexpected_status=True,
            httpx_args={"transport": transport},
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
        return _required(decide_sync.sync(client=self._decide_client, body=body))


def _required(parsed: T | None) -> T:
    if parsed is None:
        raise RuntimeError("empty response body")
    return parsed
