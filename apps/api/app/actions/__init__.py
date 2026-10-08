"""Actions registry; importing registers the generic actions (FR-40)."""

from app.actions import generic as _generic  # noqa: F401
from app.actions.jobs import handle_action_job
from app.actions.registry import (
    ActionContext,
    ActionResult,
    action,
    idem_key,
    registered,
    run_action,
)

__all__ = [
    "ActionContext",
    "ActionResult",
    "action",
    "handle_action_job",
    "idem_key",
    "registered",
    "run_action",
]
