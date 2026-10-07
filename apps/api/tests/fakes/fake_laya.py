"""Test double for the Laya client (same result shape as HttpLayaClient)."""

import asyncio
from typing import Any

FAKE_MODEL = "english"


def confident_answer(qid: str, question: dict[str, Any]) -> dict[str, Any]:
    """A confident answer for one question: first choice key / top score level / noul 0.9."""
    qtype = question.get("type", "choice")
    if qtype == "score":
        levels = len(question.get("criteria", [])) or 2
        probs = {str(i): 0.0 for i in range(levels)}
        probs[str(levels - 1)] = 0.95
        rest = 0.05 / max(levels - 1, 1)
        for key in list(probs)[:-1]:
            probs[key] = rest
        return {
            "type": "score",
            "score": levels - 1.0,
            "level": levels - 1,
            "probabilities": probs,
            "confidence": 0.95,
            "answer_confidence": 0.95,
        }
    if qtype == "noul":
        return {"type": "noul", "noul": 0.9, "confidence": 0.9, "answer_confidence": 0.9}
    keys = list(question.get("criteria", {"A": "", "B": ""}))
    probs = {k: 0.05 / max(len(keys) - 1, 1) for k in keys}
    probs[keys[0]] = 0.95
    return {
        "type": "choice",
        "choice": keys[0],
        "probabilities": probs,
        "confidence": 0.95,
        "answer_confidence": 0.95,
    }


class FakeLayaClient:
    """`responses`: one `answers` dict per state (cycled if shorter); default = confident."""

    def __init__(
        self,
        responses: list[dict[str, Any]] | None = None,
        *,
        fail: bool = False,
        latency_ms: int = 0,
    ) -> None:
        self.responses = responses
        self.fail = fail
        self.latency_ms = latency_ms
        self.calls: list[dict[str, Any]] = []

    async def batch(
        self, states: list[str], questions: dict[str, Any], *, model: str | None = None
    ) -> list[dict[str, Any] | None]:
        self.calls.append({"states": list(states), "questions": questions, "model": model})
        if self.fail:
            return [None] * len(states)
        if self.latency_ms:
            await asyncio.sleep(self.latency_ms / 1000)
        out: list[dict[str, Any] | None] = []
        for i, _ in enumerate(states):
            if self.responses:
                answers = self.responses[i % len(self.responses)]
            else:
                answers = {q: confident_answer(q, spec) for q, spec in questions.items()}
            out.append(
                {
                    "answers": answers,
                    "model": model or FAKE_MODEL,
                    "laya_version": "0.3.27",
                    "latency_ms": self.latency_ms,
                }
            )
        return out

    async def health(self) -> str:
        return "down" if self.fail else "ok"

    async def aclose(self) -> None:
        return None
