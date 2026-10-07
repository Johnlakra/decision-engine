"""HTTP client for laya-serve 0.3.27 (FR-20, FR-22, NFR-03). Never raises: failure means None."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal, Protocol

import httpx

from app.core.config import Settings

log = logging.getLogger(__name__)

BATCH_PATH = "/v1/systemone/batch"
HEALTH_PATH = "/health"
MAX_BATCH = 32  # server allows 64; stay well inside the token budget
MAX_RETRY_AFTER_S = 5.0
DEFAULT_RETRY_AFTER_S = 1.0

Health = Literal["ok", "down", "skipped"]
Sleep = Callable[[float], Awaitable[None]]


class LayaClient(Protocol):
    """Triage-model seam. A `None` entry means "no opinion" (use the LLM fallback)."""

    async def batch(
        self, states: list[str], questions: dict[str, Any], *, model: str | None = None
    ) -> list[dict[str, Any] | None]: ...


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _probs(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): p for k, v in raw.items() if (p := _num(v)) is not None}


def _parse_answer(answer: Any) -> dict[str, Any]:
    """Normalise one Laya answer to our shape; raises on an unusable one."""
    kind = answer["type"]
    if kind == "choice":
        probs = _probs(answer.get("probabilities"))
        conf = _num(answer.get("confidence"))
        out: dict[str, Any] = {
            "type": "choice",
            "choice": str(answer["choice"]),
            "probabilities": probs,
            "confidence": conf,
            "answer_confidence": _num(answer.get("answer_confidence")) or conf,
        }
    elif kind == "score":
        probs = _probs(answer.get("probabilities"))
        if not probs:
            raise ValueError("score without probabilities")
        conf = _num(answer.get("confidence"))
        out = {
            "type": "score",
            "score": _num(answer.get("score")),
            "level": int(max(probs, key=probs.__getitem__)),
            "probabilities": probs,
            "legend": answer.get("legend") or {},
            "confidence": conf,
            "answer_confidence": _num(answer.get("answer_confidence")) or conf,
        }
    elif kind == "noul":
        value = _num(answer["noul"])
        if value is None:
            raise ValueError("noul not numeric")
        conf = _num(answer.get("confidence"))
        conf = max(value, 1.0 - value) if conf is None else conf
        out = {
            "type": "noul",
            "noul": value,
            "confidence": conf,
            "answer_confidence": _num(answer.get("answer_confidence")) or conf,
        }
    else:
        raise ValueError(f"unknown answer type {kind!r}")
    return out


def _parse_result(raw: Any, latency_ms: int, version: str | None) -> dict[str, Any] | None:
    try:
        answers = {str(q): _parse_answer(a) for q, a in (raw.get("answers") or {}).items()}
        routing = raw.get("routing")
        model = routing.get("model") if isinstance(routing, dict) else None
        return {
            "answers": answers,
            "model": str(model or raw.get("model") or "unknown"),
            "laya_version": version,
            "latency_ms": latency_ms,
        }
    except (KeyError, TypeError, ValueError, AttributeError):
        log.warning("laya result unparsable")
        return None


class HttpLayaClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_s: float,
        *,
        max_batch: int = MAX_BATCH,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.base_url = base_url.strip().rstrip("/")
        self.max_batch = max(1, min(max_batch, MAX_BATCH))
        self._sleep = sleep
        self._http = httpx.AsyncClient(
            timeout=timeout_s,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    @classmethod
    def from_settings(cls, s: Settings) -> "HttpLayaClient | None":
        if not s.laya_url.strip():
            return None
        return cls(s.laya_url, s.laya_api_key.get_secret_value(), s.laya_timeout_seconds)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def health(self) -> Health:
        if not self.base_url:
            return "skipped"
        try:
            resp = await self._http.get(self.base_url + HEALTH_PATH)
            body = resp.json()
        except (httpx.HTTPError, ValueError):
            return "down"
        ok = resp.status_code == 200 and isinstance(body, dict) and body.get("status") == "ok"
        return "ok" if ok else "down"

    async def batch(
        self, states: list[str], questions: dict[str, Any], *, model: str | None = None
    ) -> list[dict[str, Any] | None]:
        if not states:
            return []
        if not self.base_url:
            return [None] * len(states)
        out: list[dict[str, Any] | None] = []
        for start in range(0, len(states), self.max_batch):
            out.extend(await self._chunk(states[start : start + self.max_batch], questions, model))
        return out

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        url = self.base_url + BATCH_PATH
        resp = await self._http.post(url, json=payload)
        if resp.status_code != 503:
            return resp
        try:
            wait = float(resp.headers.get("Retry-After", DEFAULT_RETRY_AFTER_S))
        except ValueError:
            wait = DEFAULT_RETRY_AFTER_S
        await self._sleep(min(max(wait, 0.0), MAX_RETRY_AFTER_S))
        return await self._http.post(url, json=payload)

    async def _chunk(
        self, states: list[str], questions: dict[str, Any], model: str | None
    ) -> list[dict[str, Any] | None]:
        failed: list[dict[str, Any] | None] = [None] * len(states)
        payload: dict[str, Any] = {"states": states, "questions": questions}
        if model:
            payload["model"] = model
        started = time.perf_counter()
        try:
            resp = await self._post(payload)
            if resp.status_code != 200:
                log.warning("laya batch failed status=%s", resp.status_code)
                return failed
            results = resp.json()["results"]
            if not isinstance(results, list) or len(results) != len(states):
                log.warning("laya batch result count mismatch")
                return failed
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            log.warning("laya batch error type=%s", type(exc).__name__)
            return failed
        except Exception:  # never raise into the pipeline
            log.exception("laya batch unexpected error")
            return failed
        latency_ms = int((time.perf_counter() - started) * 1000)
        version = resp.headers.get("X-Laya-Version")
        return [_parse_result(r, latency_ms, version) for r in results]
