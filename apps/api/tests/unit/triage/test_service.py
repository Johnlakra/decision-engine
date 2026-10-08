"""Triage service with fake Laya + fake LLM (FR-20..FR-25, NFR-03). No database needed."""

import uuid
from typing import Any

import pytest

from app.models import Item
from app.niches.models import NicheConfig
from app.triage import service
from app.triage.service import triage_items
from tests.fakes.fake_laya import FakeLayaClient, confident_answer
from tests.fakes.fake_llm import Failure, FakeLLM

TENANT = uuid.uuid4()
REPLY_Q = {
    "type": "choice",
    "instructions": "Reply expected?",
    "criteria": {"A": "yes", "B": "no"},
}


def make_niche(name: str, **triage: Any) -> NicheConfig:
    return NicheConfig.model_validate(
        {
            "name": name,
            "label": name,
            "description": f"things about {name}",
            "enabled": True,
            "prompt": "p",
            "actions": ["notify"],
            "autonomy": "ask",
            "triage": triage,
        }
    )


class StubRegistry:
    def __init__(self, *niches: NicheConfig) -> None:
        self._n = {n.name: n for n in niches}

    def get(self, name: str) -> NicheConfig | None:
        return self._n.get(name)

    def enabled(self) -> list[NicheConfig]:
        return list(self._n.values())


REGISTRY = StubRegistry(
    make_niche("alpha", min_confidence=0.7),
    make_niche(
        "mail",
        min_confidence=0.7,
        questions={"needs_reply": REPLY_Q},
        discard_if=[{"question": "needs_reply", "choice": "B", "min_confidence": 0.85}],
    ),
    make_niche("generic", min_confidence=0.0),
)


def item(n: int = 0, **kw: Any) -> Item:
    return Item(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        status="normalised",
        sensitivity=kw.pop("sensitivity", "public"),
        content={"title": f"Title {n}", "body": "body"},
        hints=kw.pop("hints", None),
        raw={},
        **kw,
    )


def laya_answers(
    niche: str = "alpha", conf: float = 0.95, risk: str = "normal", risk_conf: float = 0.95
) -> dict[str, Any]:
    core = {
        "needs_decision": confident_answer("n", {"criteria": {"A": "", "B": ""}}),
        "niche": confident_answer("n", {"criteria": {niche: "", "zzz": ""}}),
        "urgency": confident_answer("u", {"type": "score", "criteria": ["a", "b", "c"]}),
        "risk": confident_answer("r", {"criteria": {risk: "", "other": ""}}),
    }
    for answer in core.values():
        answer["confidence"] = conf
    core["risk"]["confidence"] = risk_conf
    return core


def llm_reply(niche: str = "alpha", risk: str = "normal", risk_conf: float = 0.9) -> dict[str, Any]:
    return {
        "needs_decision": {"choice": "A", "confidence": 0.8},
        "niche": {"choice": niche, "confidence": 0.8},
        "urgency": {"level": 1, "confidence": 0.7},
        "risk": {"choice": risk, "confidence": risk_conf},
    }


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"settings": {}, "emitted": [], "laya": None}

    async def load(session: Any, tenant_ids: set[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
        return {TENANT: state["settings"]}

    async def emit(session: Any, **kwargs: Any) -> None:
        state["emitted"].append(kwargs)

    monkeypatch.setattr(service, "_load_settings", load)
    monkeypatch.setattr(service.events, "emit", emit)
    monkeypatch.setattr(service, "get_laya_client", lambda: state["laya"])
    monkeypatch.delenv("LAYA_MODE", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield state
    get_settings.cache_clear()


async def run(items: list[Item]) -> list[service.TriageOutcome]:
    return await triage_items(None, items, registry=REGISTRY)  # type: ignore[arg-type]


async def test_forty_items_one_laya_call_shadow_default(
    env: dict[str, Any], fake_llm: FakeLLM
) -> None:
    laya = env["laya"] = FakeLayaClient([laya_answers()])
    fake_llm.script("classify", llm_reply(), repeat=True)
    items = [item(i) for i in range(40)]
    outcomes = await run(items)
    assert len(laya.calls) == 1 and len(laya.calls[0]["states"]) == 40
    assert {o.status for o in outcomes} == {"triaged"}
    t = items[0].triage
    assert t["mode"] == "shadow" and t["decided_by"] == "llm_fallback"
    assert t["shadow"]["answers"]["niche"]["choice"] == "alpha"
    assert t["shadow"]["error"] is None
    assert items[0].niche == "alpha" and items[0].urgency == 1 and items[0].laya_mode == "shadow"
    assert len(env["emitted"]) == 40 and env["emitted"][0]["event"] == "item.triaged"


async def test_off_mode_never_calls_laya(env: dict[str, Any], fake_llm: FakeLLM) -> None:
    laya = env["laya"] = FakeLayaClient()
    env["settings"] = {"laya_mode": "off"}
    fake_llm.script("classify", llm_reply())
    it = item()
    await run([it])
    assert laya.calls == []
    assert it.triage["mode"] == "off" and it.triage["shadow"] is None
    assert it.triage["answers"]["niche"]["source"] == "llm_fallback"


async def test_on_mode_confident_laya_needs_no_llm(env: dict[str, Any], fake_llm: FakeLLM) -> None:
    env["laya"] = FakeLayaClient([laya_answers()])
    env["settings"] = {"laya_mode": "on"}
    it = item()
    await run([it])
    assert fake_llm.calls == []
    assert it.triage["decided_by"] == "laya" and it.triage["fallback"] is False
    assert it.triage["answers"]["niche"]["source"] == "laya"


async def test_on_mode_low_confidence_questions_go_to_fallback(
    env: dict[str, Any], fake_llm: FakeLLM
) -> None:
    answers = laya_answers()
    answers["urgency"]["confidence"] = 0.2
    env["laya"] = FakeLayaClient([answers])
    env["settings"] = {"laya_mode": "on"}
    fake_llm.script("classify", {"urgency": {"level": 0, "confidence": 0.9}})
    it = item()
    await run([it])
    call = fake_llm.calls_for("classify")[0]
    assert it.triage["answers"]["urgency"]["source"] == "llm_fallback"
    assert it.triage["answers"]["niche"]["source"] == "laya"
    assert it.triage["decided_by"] == "llm_fallback" and it.triage["fallback"] is True
    assert call.schema is not None and list(call.schema.model_fields) == ["q0"]


async def test_niche_override_turns_on_for_that_niche_only(
    env: dict[str, Any], fake_llm: FakeLLM
) -> None:
    env["laya"] = FakeLayaClient([laya_answers("alpha")])
    env["settings"] = {"laya_mode": "shadow", "laya_mode_by_niche": {"alpha": "on"}}
    it = item()
    await run([it])
    assert it.triage["mode"] == "on" and fake_llm.calls == []


async def test_shadow_laya_down_records_error_and_uses_llm(
    env: dict[str, Any], fake_llm: FakeLLM
) -> None:
    env["laya"] = FakeLayaClient(fail=True)
    fake_llm.script("classify", llm_reply())
    it = item()
    outcomes = await run([it])
    assert outcomes[0].status == "triaged"
    assert it.triage["decided_by"] == "llm_fallback"
    assert it.triage["shadow"]["error"] == "laya_unavailable"


async def test_on_mode_laya_down_uses_llm(env: dict[str, Any], fake_llm: FakeLLM) -> None:
    env["laya"] = FakeLayaClient(fail=True)
    env["settings"] = {"laya_mode": "on"}
    fake_llm.script("classify", llm_reply())
    it = item()
    await run([it])
    assert it.triage["mode"] == "on" and it.triage["decided_by"] == "llm_fallback"


async def test_no_laya_client_configured_still_triages(
    env: dict[str, Any], fake_llm: FakeLLM
) -> None:
    fake_llm.script("classify", llm_reply())
    it = item()
    assert (await run([it]))[0].status == "triaged"
    assert it.triage["shadow"]["error"] == "laya_unavailable"


async def test_laya_and_llm_down_needs_human_triage(env: dict[str, Any], fake_llm: FakeLLM) -> None:
    env["laya"] = FakeLayaClient(fail=True)
    fake_llm.script("classify", Failure.TIMEOUT, repeat=True)
    items = [item(i) for i in range(3)]
    outcomes = await run(items)
    assert {o.status for o in outcomes} == {"needs_human_triage"}
    assert items[0].triage["error"] == "fallback_unavailable"
    assert env["emitted"] == []


async def test_private_item_classified_with_private_sensitivity(
    env: dict[str, Any], fake_llm: FakeLLM
) -> None:
    fake_llm.script("classify", llm_reply())
    await run([item(sensitivity="private")])
    assert fake_llm.calls_for("classify")[0].sensitivity == "private"


async def test_hinted_niche_sets_hint_source_and_asks_niche_questions_in_same_call(
    env: dict[str, Any], fake_llm: FakeLLM
) -> None:
    laya = env["laya"] = FakeLayaClient()
    fake_llm.script(
        "classify",
        {
            **{k: v for k, v in llm_reply().items() if k != "niche"},
            "needs_reply": {"choice": "A", "confidence": 0.9},
        },
    )
    it = item(hints={"niche": "mail"})
    await run([it])
    assert len(laya.calls) == 1
    assert "needs_reply" in laya.calls[0]["questions"] and "niche" not in laya.calls[0]["questions"]
    assert it.triage["answers"]["niche"]["source"] == "hint"
    assert it.niche == "mail"


async def test_unhinted_niche_questions_get_second_laya_call_per_group(
    env: dict[str, Any], fake_llm: FakeLLM
) -> None:
    laya = env["laya"] = FakeLayaClient()
    env["settings"] = {"laya_mode": "on"}
    laya.responses = None
    items = [item(i) for i in range(2)]

    async def first(states: list[str], questions: dict[str, Any], *, model: Any = None) -> Any:
        laya.calls.append({"states": states, "questions": questions, "model": model})
        if "niche" in questions:
            return [
                {
                    "answers": laya_answers("mail"),
                    "model": "english",
                    "laya_version": "0.3.27",
                    "latency_ms": 5,
                }
                for _ in states
            ]
        return [
            {
                "answers": {
                    "needs_reply": {
                        **confident_answer("q", REPLY_Q),
                        "choice": "B",
                        "confidence": 0.95,
                    }
                },
                "model": "english",
                "laya_version": "0.3.27",
                "latency_ms": 4,
            }
            for _ in states
        ]

    laya.batch = first  # type: ignore[method-assign]
    outcomes = await run(items)
    assert len(laya.calls) == 2
    assert len(laya.calls[1]["states"]) == 2 and list(laya.calls[1]["questions"]) == ["needs_reply"]
    assert {o.status for o in outcomes} == {"discarded"}  # discard_if needs_reply=B >= 0.85
    assert fake_llm.calls == []


async def test_spam_is_discarded_and_scam_is_kept_with_risk(
    env: dict[str, Any], fake_llm: FakeLLM
) -> None:
    fake_llm.script(
        "classify",
        llm_reply(risk="spam", risk_conf=0.9),
        llm_reply(risk="scam_or_phishing", risk_conf=0.9),
    )
    spam, scam = item(1), item(2)
    outcomes = await run([spam, scam])
    assert {o.item_id: o.status for o in outcomes} == {spam.id: "discarded", scam.id: "triaged"}
    assert scam.risk == "scam_or_phishing"


async def test_items_not_awaiting_triage_are_left_alone(
    env: dict[str, Any], fake_llm: FakeLLM
) -> None:
    done = item()
    done.status = "triaged"
    outcomes = await run([done])
    assert outcomes[0].status == "triaged" and done.triage is None
    assert env["emitted"] == []
