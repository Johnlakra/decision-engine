"""Today's numbers for the dashboard: ``GET /v1/stats/today`` (FR-60, FR-64). Read-only."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.core.config import get_settings
from app.core.time import utcnow
from app.db import stats as queries
from app.db.session import get_session
from app.llm.config import load_config
from app.models import TenantSettings
from app.schemas.stats import StatsToday
from app.security.api_keys import Principal
from app.triage.modes import resolve_mode

router = APIRouter(prefix="/stats", tags=["stats"])

Reader = Annotated[Principal, Depends(require_scope("items:read"))]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "/today",
    response_model=StatsToday,
    summary="Today's item counts, LLM budget use and Laya agreement (UTC day)",
    operation_id="get_stats_today",
)
async def stats_today(principal: Reader, session: Session) -> StatsToday:
    now = utcnow()
    since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tenant_id = principal.tenant_id
    items = await queries.item_counts(session, tenant_id, since)
    decided, auto_handled = await queries.decision_counts(session, tenant_id, since)
    row = await session.get(TenantSettings, tenant_id)
    mode = resolve_mode(dict(row.settings) if row else {}, None, get_settings().laya_mode)
    return StatsToday(
        date=now.date().isoformat(),
        items_in=items["items_in"],
        decided=decided,
        auto_handled=auto_handled,
        discarded=items["discarded"],
        by_status=items["by_status"],
        by_niche=items["by_niche"],
        llm=await queries.llm_budgets(session, tenant_id, since, load_config()),
        laya_mode=mode,
        laya_agreement=await queries.shadow_agreement(session, tenant_id, since),
    )
