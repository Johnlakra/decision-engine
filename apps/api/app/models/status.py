"""Item status machine (ARCHITECTURE.md §2). ``transition`` is the only writer of items.status."""

from collections.abc import Mapping
from typing import Protocol

from app.models.enums import ItemStatus as S


class InvalidTransition(ValueError):  # noqa: N818 - name fixed by the contract
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"invalid item transition: {current} -> {target}")
        self.current = current
        self.target = target


class HasStatus(Protocol):
    status: str


_FLOW: dict[S, frozenset[S]] = {
    S.NEW: frozenset({S.NORMALISED}),
    S.NORMALISED: frozenset({S.TRIAGED, S.NEEDS_HUMAN_TRIAGE, S.DISCARDED}),  # dedupe -> discarded
    S.TRIAGED: frozenset({S.INFORMATIONAL, S.DISCARDED, S.DECIDING}),
    S.NEEDS_HUMAN_TRIAGE: frozenset({S.TRIAGED}),
    S.INFORMATIONAL: frozenset({S.DONE}),
    S.DISCARDED: frozenset(),
    S.DECIDING: frozenset({S.AWAITING_APPROVAL}),
    S.AWAITING_APPROVAL: frozenset({S.APPROVED, S.REJECTED, S.SNOOZED, S.AUTO_APPROVED}),
    S.APPROVED: frozenset({S.ACTING}),
    S.AUTO_APPROVED: frozenset({S.ACTING}),
    S.REJECTED: frozenset({S.DONE}),
    S.SNOOZED: frozenset({S.AWAITING_APPROVAL}),
    S.ACTING: frozenset({S.DONE}),
    S.DONE: frozenset(),
    S.FAILED: frozenset({S.NEW}),  # the UI "retry" restarts the pipeline
}

_FAILABLE = frozenset(S) - {S.DONE, S.DISCARDED, S.FAILED}  # "any step -> failed"

ALLOWED_TRANSITIONS: Mapping[S, frozenset[S]] = {
    state: targets | ({S.FAILED} if state in _FAILABLE else frozenset())
    for state, targets in _FLOW.items()
}


def can_transition(current: str, to: S) -> bool:
    try:
        return to in ALLOWED_TRANSITIONS[S(current)]
    except ValueError:
        return False


def transition(item: HasStatus, to: S) -> None:
    """Move ``item`` to ``to`` or raise InvalidTransition. Never write items.status elsewhere."""
    if not can_transition(item.status, to):
        raise InvalidTransition(str(item.status), str(to))
    item.status = to.value
