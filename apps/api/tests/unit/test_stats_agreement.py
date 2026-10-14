"""Laya agreement helper behind /v1/stats/today (FR-64)."""

from app.db.stats import laya_agreement


def _a(**choices: str) -> dict[str, dict[str, str]]:
    return {q: {"choice": c} for q, c in choices.items()}


def test_no_pairs_is_none() -> None:
    assert laya_agreement([]) is None


def test_only_shared_questions_with_a_choice_count() -> None:
    pairs = [
        (_a(niche="inbox", risk="none"), _a(niche="inbox", risk="scam")),  # 1 of 2
        (_a(niche="inbox"), _a(urgency="1")),  # no shared question
        ({"niche": {"score": 0.4}}, _a(niche="inbox")),  # own side has no choice
    ]
    assert laya_agreement(pairs) == 0.5


def test_garbled_shapes_are_ignored() -> None:
    assert laya_agreement([("x", None), (None, ["y"]), ({"q": 3}, {"q": 3})]) is None
