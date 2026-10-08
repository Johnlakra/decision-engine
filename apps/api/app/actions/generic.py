"""Generic actions with no external side effects beyond events and jobs (FR-40, NFR-07).

Param models forbid extras and carry no URL or email fields.
"""

from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.actions.registry import ActionContext, ActionResult, action
from app.models import Item
from app.models.enums import JobKind
from app.workers import queue

MAX_LABEL = 40


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoParams(_Strict):
    pass


class LabelParams(_Strict):
    label: str = Field(min_length=1, max_length=MAX_LABEL)


class RemindParams(_Strict):
    until: AwareDatetime


class CreateTaskParams(_Strict):
    title: str | None = Field(default=None, max_length=500)
    due: AwareDatetime | None = None


@action("archive", reversible=True, params=NoParams)
async def archive(ctx: ActionContext, params: NoParams) -> ActionResult:
    return ActionResult(True, {"archived": True})


@action("label", reversible=True, params=LabelParams)
async def label(ctx: ActionContext, params: LabelParams) -> ActionResult:
    return ActionResult(True, {"label": params.label})


async def _schedule_reminder(ctx: ActionContext, until: datetime) -> ActionResult:
    await queue.enqueue(
        ctx.session,
        tenant_id=ctx.tenant_id,
        kind=JobKind.ACTION,
        item_id=ctx.item_id,
        payload={"op": "reminder_due", "action_log_id": str(ctx.action_log_id)},
        run_at=until,
    )
    return ActionResult(True, {"until": until.isoformat()})


@action("snooze", params=RemindParams)
async def snooze(ctx: ActionContext, params: RemindParams) -> ActionResult:
    return await _schedule_reminder(ctx, params.until)


@action("remind", params=RemindParams)
async def remind(ctx: ActionContext, params: RemindParams) -> ActionResult:
    return await _schedule_reminder(ctx, params.until)


@action("create_task", params=CreateTaskParams)
async def create_task(ctx: ActionContext, params: CreateTaskParams) -> ActionResult:
    title = params.title
    if not title:
        item = await ctx.session.get(Item, ctx.item_id)
        title = ((item.content or {}).get("title") if item else None) or "Task"
    task = {
        "title": title,
        "due": params.due.isoformat() if params.due else None,
        "item_id": str(ctx.item_id),
    }
    return ActionResult(True, {"task": task})


@action("webhook", params=NoParams)
async def webhook(ctx: ActionContext, params: NoParams) -> ActionResult:
    """Marker: delivery happens through the `action.done` event the act node emits (C2)."""
    return ActionResult(True, {"delivers_via": "action.done"})
