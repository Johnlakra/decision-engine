"""POST /v1/decide against the ASGI app (FR-35, FR-96)."""

from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.triage.service as triage_service
from app.core.config import get_settings
from app.models import ActionLog, Decision, Feedback, Item, Job
from app.security.api_keys import create_api_key
from tests.fakes.fake_laya import FakeLayaClient
from tests.fakes.fake_llm import FakeLLM, fake_llm  # noqa: F401
from tests.integration.graph_support import (
    DECISION_OUT,
    bearer,
    mini_client,  # noqa: F401
    real_niches,  # noqa: F401
)

pytestmark = pytest.mark.integration

SessionFactory = async_sessionmaker[AsyncSession]
QUESTIONS = {
    "sell": {
        "type": "choice",
        "instructions": "Sell the wheat now or hold?",
        "criteria": {"A": "sell now", "B": "hold 1-2 weeks"},
    }
}


def use_laya(monkeypatch: pytest.MonkeyPatch, client: Any) -> Any:
    monkeypatch.setattr(triage_service, "get_laya_client", lambda: client)
    return client


async def row_counts(factory: SessionFactory) -> dict[str, int]:
    async with factory() as session:
        return {
            model.__name__: (await session.scalar(select(func.count()).select_from(model))) or 0
            for model in (Item, Decision, Feedback, ActionLog, Job)
        }


async def post(client: httpx.AsyncClient, key: str, body: dict[str, Any]) -> httpx.Response:
    return await client.post("/v1/decide", json=body, headers=bearer(key))


async def test_laya_answers_with_no_llm_call_and_no_rows(
    mini_client: httpx.AsyncClient,  # noqa: F811
    committed_db: SessionFactory,
    admin_key: str,
    fake_llm: FakeLLM,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_laya(monkeypatch, FakeLayaClient())

    response = await post(mini_client, admin_key, {"state": "wheat 2200", "questions": QUESTIONS})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["fallback"] is False and body["model"] == "english"
    assert body["answers"]["sell"]["choice"] == "A"
    assert body["decision"] is None and body["explanation"] is None
    assert fake_llm.calls == []
    assert set((await row_counts(committed_db)).values()) == {0}


async def test_laya_down_reports_fallback(
    mini_client: httpx.AsyncClient,  # noqa: F811
    admin_key: str,
    fake_llm: FakeLLM,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_laya(monkeypatch, FakeLayaClient(fail=True))
    fake_llm.script("classify", {"sell": {"choice": "B", "confidence": 0.7}})

    response = await post(
        mini_client, admin_key, {"state": {"crop": "wheat"}, "questions": QUESTIONS}
    )

    assert response.status_code == 200
    assert response.json()["fallback"] is True
    assert response.json()["answers"]["sell"]["source"] == "llm_fallback"


async def test_niche_decision_writes_no_item_rows(
    mini_client: httpx.AsyncClient,  # noqa: F811
    committed_db: SessionFactory,
    admin_key: str,
    fake_llm: FakeLLM,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_laya(monkeypatch, FakeLayaClient())
    fake_llm.script("normalise", {"entities": {}}).script("decide", DECISION_OUT)

    response = await post(
        mini_client,
        admin_key,
        {"state": "Pay the bill?", "questions": QUESTIONS, "niche": "generic"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["decision"]["recommended"] == "A"
    assert response.json()["decision"]["autonomy"] == "ask"
    assert set((await row_counts(committed_db)).values()) == {0}


async def test_explain_returns_explanation(
    mini_client: httpx.AsyncClient,  # noqa: F811
    admin_key: str,
    fake_llm: FakeLLM,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_laya(monkeypatch, FakeLayaClient())
    fake_llm.script("decide", "Prices are low now.")

    response = await post(
        mini_client, admin_key, {"state": "wheat", "questions": QUESTIONS, "explain": True}
    )

    assert response.json()["explanation"] == "Prices are low now."


async def test_invalid_questions_and_unknown_niche_are_422(
    mini_client: httpx.AsyncClient,  # noqa: F811
    admin_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_laya(monkeypatch, FakeLayaClient())

    bad_question = await post(mini_client, admin_key, {"state": "x", "questions": {"q": {"x": 1}}})
    bad_niche = await post(mini_client, admin_key, {"state": "x", "niche": "nope"})
    bad_sensitivity = await post(mini_client, admin_key, {"state": "x", "sensitivity": "secret"})

    assert (bad_question.status_code, bad_niche.status_code) == (422, 422)
    assert bad_sensitivity.status_code == 422
    assert bad_question.headers["content-type"].startswith("application/problem+json")


async def test_private_without_private_provider_is_503(
    mini_client: httpx.AsyncClient,  # noqa: F811
    admin_key: str,
    fake_llm: FakeLLM,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_laya(monkeypatch, FakeLayaClient(fail=True))
    fake_llm.private_available = False
    fake_llm.script("classify", {"sell": {"choice": "B", "confidence": 0.7}})

    response = await post(
        mini_client,
        admin_key,
        {"state": "x", "questions": QUESTIONS, "sensitivity": "private"},
    )

    assert response.status_code == 503
    assert response.json()["type"].endswith("/no-private-provider")


async def test_fallback_unavailable_is_503(
    mini_client: httpx.AsyncClient,  # noqa: F811
    admin_key: str,
    fake_llm: FakeLLM,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_laya(monkeypatch, FakeLayaClient(fail=True))

    response = await post(mini_client, admin_key, {"state": "x", "questions": QUESTIONS})

    assert response.status_code == 503
    assert response.json()["type"].endswith("/llm-unavailable")


async def test_slow_laya_times_out_with_504(
    mini_client: httpx.AsyncClient,  # noqa: F811
    admin_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DECIDE_TIMEOUT_SECONDS", "0.05")
    get_settings.cache_clear()
    use_laya(monkeypatch, FakeLayaClient(latency_ms=2000))

    response = await post(mini_client, admin_key, {"state": "x", "questions": QUESTIONS})

    assert response.status_code == 504


async def test_requires_decide_scope(
    mini_client: httpx.AsyncClient,  # noqa: F811
    committed_db: SessionFactory,
    tenant_committed: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_laya(monkeypatch, FakeLayaClient())
    pepper = get_settings().api_key_pepper.get_secret_value()
    async with committed_db() as session:
        reader = await create_api_key(session, tenant_committed.id, "r", ["items:read"], pepper)
        caller = await create_api_key(session, tenant_committed.id, "d", ["decide"], pepper)
        await session.commit()

    denied = await post(mini_client, reader, {"state": "x", "questions": QUESTIONS})
    allowed = await post(mini_client, caller, {"state": "x", "questions": QUESTIONS})

    assert (denied.status_code, allowed.status_code) == (403, 200)
