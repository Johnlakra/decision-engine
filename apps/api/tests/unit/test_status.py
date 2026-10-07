"""Item status machine (ARCHITECTURE.md §2)."""

from types import SimpleNamespace

import pytest

from app.models.enums import ItemStatus as S
from app.models.status import ALLOWED_TRANSITIONS, InvalidTransition, transition

VALID = [
    (S.NEW, S.NORMALISED),
    (S.NORMALISED, S.TRIAGED),
    (S.NORMALISED, S.NEEDS_HUMAN_TRIAGE),
    (S.NORMALISED, S.DISCARDED),
    (S.TRIAGED, S.INFORMATIONAL),
    (S.TRIAGED, S.DISCARDED),
    (S.TRIAGED, S.DECIDING),
    (S.INFORMATIONAL, S.DONE),
    (S.DECIDING, S.AWAITING_APPROVAL),
    (S.AWAITING_APPROVAL, S.APPROVED),
    (S.AWAITING_APPROVAL, S.REJECTED),
    (S.AWAITING_APPROVAL, S.SNOOZED),
    (S.AWAITING_APPROVAL, S.AUTO_APPROVED),
    (S.APPROVED, S.ACTING),
    (S.AUTO_APPROVED, S.ACTING),
    (S.REJECTED, S.DONE),
    (S.SNOOZED, S.AWAITING_APPROVAL),
    (S.ACTING, S.DONE),
    (S.FAILED, S.NEW),
    (S.DECIDING, S.FAILED),
]
INVALID = [
    (S.NEW, S.DONE),
    (S.NEW, S.TRIAGED),
    (S.DONE, S.NEW),
    (S.DONE, S.FAILED),
    (S.DISCARDED, S.TRIAGED),
    (S.AWAITING_APPROVAL, S.ACTING),
    (S.REJECTED, S.ACTING),
    (S.NORMALISED, S.NORMALISED),
]


@pytest.mark.parametrize(("current", "target"), VALID)
def test_valid_transition_updates_status(current: S, target: S) -> None:
    item = SimpleNamespace(status=current.value)
    transition(item, target)
    assert item.status == target.value


@pytest.mark.parametrize(("current", "target"), INVALID)
def test_invalid_transition_raises_and_keeps_status(current: S, target: S) -> None:
    item = SimpleNamespace(status=current.value)
    with pytest.raises(InvalidTransition):
        transition(item, target)
    assert item.status == current.value


def test_every_status_is_in_the_table() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(S)
