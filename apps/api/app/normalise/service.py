"""normalise_item: new -> normalised (C6, FR-10..13). Priority: hint > LLM > heuristic."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item
from app.models.enums import ItemStatus
from app.models.status import transition
from app.normalise.language import detect_language
from app.normalise.llm_normaliser import llm_normalise
from app.normalise.mappers import map_payload


def _language_text(content: dict[str, Any]) -> str:
    return f"{content.get('title', '')}\n{content.get('body', '')}"[:2000]


async def normalise_item(session: AsyncSession, item: Item) -> None:
    """Set items.content and items.language, then move to `normalised`. No commit here."""
    hints = item.hints or {}
    content = map_payload(item.source, item.raw, hints)
    if content is None:
        content = await llm_normalise(
            source=item.source,
            payload=item.raw,
            sensitivity=item.sensitivity,
            item_id=str(item.id),
        )
    language = (
        hints.get("language")
        or content.language
        or detect_language(_language_text(content.model_dump()))
    )
    content = content.model_copy(update={"language": language})
    transition(item, ItemStatus.NORMALISED)  # validate first: nothing is written on a bad state
    item.content = content.model_dump(mode="json")
    item.language = language
