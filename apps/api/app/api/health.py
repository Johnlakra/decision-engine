"""Liveness probe: no database, no Redis (NFR-08)."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["health"])


class Liveness(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "ok"}]})

    status: Literal["ok"] = "ok"


@router.get(
    "/health",
    response_model=Liveness,
    summary="Liveness",
    operation_id="health",
    responses={
        200: {
            "description": "The process is up",
            "content": {"application/json": {"example": {"status": "ok"}}},
        }
    },
)
async def health() -> Liveness:
    return Liveness()
