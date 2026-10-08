"""Raw Laya answers to validated `Answer` objects (garbled = no opinion for that question)."""

from collections.abc import Mapping
from typing import Any

from app.schemas.triage import Answer


def hint_answer(niche: str) -> Answer:
    return Answer(
        type="choice", choice=niche, probabilities={niche: 1.0}, confidence=1.0, source="hint"
    )


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def laya_answer(spec: Mapping[str, Any], raw: Any) -> Answer | None:
    """Validate against the question that was asked; None when unusable."""
    if not isinstance(raw, Mapping) or raw.get("type") != spec.get("type", "choice"):
        return None
    probs_raw = raw.get("probabilities")
    probs = (
        {str(k): p for k, v in probs_raw.items() if (p := _num(v)) is not None}
        if isinstance(probs_raw, Mapping)
        else {}
    )
    conf = _num(raw.get("confidence"))
    criteria = spec["criteria"]
    kind = raw["type"]
    if kind == "choice":
        choice = raw.get("choice")
        if not isinstance(choice, str) or choice not in criteria:
            return None
        return Answer(
            type="choice", choice=choice, probabilities=probs, confidence=conf, source="laya"
        )
    if kind == "score":
        level = raw.get("level")
        if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level < len(criteria):
            return None
        return Answer(
            type="score",
            score=_num(raw.get("score")),
            level=level,
            probabilities=probs,
            confidence=conf,
            source="laya",
        )
    noul = _num(raw.get("noul"))
    if noul is None:
        return None
    return Answer(type="noul", noul=noul, probabilities={}, confidence=conf, source="laya")


def parse_laya_result(
    questions: Mapping[str, Any], result: Mapping[str, Any] | None
) -> dict[str, Answer]:
    """Usable answers only; an empty dict means no opinion."""
    if not result or not isinstance(result.get("answers"), Mapping):
        return {}
    out: dict[str, Answer] = {}
    for qid, spec in questions.items():
        parsed = laya_answer(spec, result["answers"].get(qid))
        if parsed is not None:
            out[qid] = parsed
    return out
