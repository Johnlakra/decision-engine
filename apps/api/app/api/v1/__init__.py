"""Version 1 routes."""

from fastapi import APIRouter

from app.api.v1 import niches

router = APIRouter(prefix="/v1")
router.include_router(niches.router)

__all__ = ["router"]
