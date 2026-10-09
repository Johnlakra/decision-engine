"""Version 1 routes."""

from fastapi import APIRouter

from app.api.v1 import decide, decisions, feedback, items, niches, subscriptions

router = APIRouter(prefix="/v1")
router.include_router(items.router)
router.include_router(decisions.router)
router.include_router(decide.router)
router.include_router(subscriptions.router)
router.include_router(feedback.router)
router.include_router(niches.router)

__all__ = ["router"]
