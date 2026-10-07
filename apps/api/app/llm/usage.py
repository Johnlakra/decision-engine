"""llm_usage logging with the INR cost estimate (FR-62). Never raises into the caller."""

import logging
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.llm.budgets import SessionFactory
from app.llm.config import ProviderConfig
from app.models import Tenant
from app.models.llm_usage import LlmUsage

logger = logging.getLogger(__name__)

_COST_QUANT = Decimal("0.0001")
_tenant_id: uuid.UUID | None = None


def estimate_cost_inr(
    provider: ProviderConfig, prompt_tokens: int, completion_tokens: int
) -> Decimal:
    """INR estimate from the prices table in providers.yaml (0 for free tiers)."""
    total = (
        Decimal(str(provider.price_in_inr_per_1m)) * prompt_tokens
        + Decimal(str(provider.price_out_inr_per_1m)) * completion_tokens
    ) / Decimal(1_000_000)
    return total.quantize(_COST_QUANT)


def reset_tenant_cache() -> None:
    global _tenant_id
    _tenant_id = None


def _parse_item_id(item_id: str | None) -> uuid.UUID | None:
    if not item_id:
        return None
    try:
        return uuid.UUID(item_id)
    except ValueError:
        return None


async def record_usage(
    session_factory: SessionFactory,
    *,
    provider: ProviderConfig,
    purpose: str,
    item_id: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    ok: bool,
    error_code: str | None,
) -> None:
    """Write one row per attempt. Single-tenant MVP: attributes to the oldest tenant."""
    global _tenant_id
    try:
        async with session_factory() as session:
            if _tenant_id is None:
                _tenant_id = (
                    await session.execute(select(Tenant.id).order_by(Tenant.created_at).limit(1))
                ).scalar_one_or_none()
            if _tenant_id is None:
                logger.warning("llm_usage not recorded: no tenant row yet")
                return
            session.add(
                LlmUsage(
                    tenant_id=_tenant_id,
                    provider=provider.name,
                    model=provider.litellm_model,
                    purpose=purpose,
                    item_id=_parse_item_id(item_id),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_inr=estimate_cost_inr(provider, prompt_tokens, completion_tokens),
                    latency_ms=latency_ms,
                    ok=ok,
                    error_code=error_code,
                )
            )
            await session.flush()
    except Exception:
        _tenant_id = None
        logger.warning("llm_usage write failed", exc_info=True, extra={"provider": provider.name})
