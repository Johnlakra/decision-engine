"""Stored answer shape, discard thresholds and scam handling (FR-22, FR-24, FR-25)."""

from typing import Any

import pytest

from app.graph.nodes.policy import choose_autonomy, is_scam
from app.niches.models import NicheConfig
from app.schemas.decision import DecisionOut
from tests.fakes.fake_llm import Failure, FakeLLM
from tests.unit.triage.test_service import (  # noqa: F401 - env is a fixture
    env,
    item,
    laya_answers,
    llm_reply,
    run,
)

SPAM_THRESHOLD = 0.85


@pytest.fixture
def laya_on(env: dict[str, Any]) -> dict[str, Any]:  # noqa: F811
    from tests.fakes.fake_laya import FakeLayaClient

    env["settings"] = {"laya_mode": "on"}
    env["laya_cls"] = FakeLayaClient
    return env


async def test_every_stored_answer_has_choice_probabilities_confidence_and_model(
    laya_on: dict[str, Any],
) -> None:
    laya_on["laya"] = laya_on["laya_cls"]([laya_answers()])
    it = item()
    await run([it])

    record = it.triage
    assert record["model"] and record["laya_version"] == "0.3.27"
    for qid in ("needs_decision", "niche", "risk"):
        answer = record["answers"][qid]
        assert answer["choice"] and answer["source"] == "laya"
        assert answer["probabilities"] and 0 <= answer["confidence"] <= 1
    urgency = record["answers"]["urgency"]
    assert urgency["level"] is not None and urgency["probabilities"]


@pytest.mark.parametrize(
    ("risk_conf", "status"), [(0.84, "triaged"), (SPAM_THRESHOLD, "discarded"), (0.99, "discarded")]
)
async def test_spam_discard_threshold(
    laya_on: dict[str, Any], risk_conf: float, status: str
) -> None:
    laya_on["laya"] = laya_on["laya_cls"]([laya_answers(risk="spam", risk_conf=risk_conf)])
    it = item()
    await run([it])
    assert it.status == status
    assert it.risk == "spam"


async def test_scam_is_never_discarded_even_when_certain(laya_on: dict[str, Any]) -> None:
    laya_on["laya"] = laya_on["laya_cls"]([laya_answers(risk="scam_or_phishing", risk_conf=1.0)])
    it = item()
    await run([it])
    assert it.status == "triaged" and it.risk == "scam_or_phishing"


async def test_discarded_item_keeps_its_triage_record(laya_on: dict[str, Any]) -> None:
    laya_on["laya"] = laya_on["laya_cls"]([laya_answers(risk="spam", risk_conf=0.95)])
    it = item()
    await run([it])
    assert it.status == "discarded" and it.triage["answers"]["risk"]["choice"] == "spam"


async def test_human_triage_item_has_error_and_no_niche(
    env: dict[str, Any],  # noqa: F811
    fake_llm: FakeLLM,
) -> None:
    from tests.fakes.fake_laya import FakeLayaClient

    env["laya"] = FakeLayaClient(fail=True)
    fake_llm.script("classify", Failure.RATE_LIMIT_429, repeat=True)
    it = item()
    await run([it])
    assert it.status == "needs_human_triage"
    assert it.triage["error"] and it.niche is None


@pytest.mark.parametrize(
    ("confidence", "expected"), [(0.8, True), (0.79, False), (0.99, True), (None, True)]
)
def test_scam_boundary_is_inclusive_at_point_eight(
    confidence: float | None, expected: bool
) -> None:
    answers = {"risk": {} if confidence is None else {"confidence": confidence}}
    assert is_scam("scam_or_phishing", {"answers": answers}) is expected


@pytest.mark.parametrize("risk", [None, "normal", "spam"])
def test_non_scam_risk_is_never_scam(risk: str | None) -> None:
    assert not is_scam(risk, {"answers": {"risk": {"confidence": 0.99}}})


def test_scam_overrides_auto_autonomy_with_allow_listed_action() -> None:
    niche = NicheConfig.model_validate(
        {
            "name": "x", "label": "x", "description": "d", "enabled": True, "prompt": "p",
            "actions": ["archive"], "autonomy": "auto", "auto_actions": ["archive"],
        }
    )  # fmt: skip
    decision = DecisionOut.model_validate(
        {
            "options": [
                {"id": "A", "label": "a", "actions": [{"type": "archive"}]},
                {"id": "B", "label": "b"},
            ],
            "recommended": "A", "rationale": "r", "confidence": 0.9,
        }
    )  # fmt: skip
    assert choose_autonomy(niche, decision, scam=False, expert=False) == "auto"
    assert choose_autonomy(niche, decision, scam=True, expert=False) == "suggest"


# FR-21, FR-24: fallback niche (min_confidence 0.0) must not accept low-confidence answers
def test_gate_uses_default_for_fallback_and_unrouted_items() -> None:
    from types import SimpleNamespace

    from app.niches.registry import FALLBACK_NICHE
    from app.triage.service import DEFAULT_GATE, _gate

    generic = SimpleNamespace(name=FALLBACK_NICHE, triage=SimpleNamespace(min_confidence=0.0))
    niche = SimpleNamespace(name="email", triage=SimpleNamespace(min_confidence=0.6))
    registry = SimpleNamespace(get=lambda n: {FALLBACK_NICHE: generic, "email": niche}.get(n))
    work = SimpleNamespace(hinted=None)
    assert _gate(work, None, registry) == DEFAULT_GATE  # type: ignore[arg-type]
    assert _gate(work, FALLBACK_NICHE, registry) == DEFAULT_GATE  # type: ignore[arg-type]
    assert _gate(SimpleNamespace(hinted=generic), None, registry) == DEFAULT_GATE  # type: ignore[arg-type]
    assert _gate(work, "email", registry) == 0.6  # type: ignore[arg-type]
