"""Webhook subscriptions, admin only (FR-42). The secret is write-only."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.core.errors import ProblemError
from app.db.session import get_session
from app.integrations import subscriptions as service
from app.models import WebhookSubscription
from app.security.api_keys import Principal

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

Session = Annotated[AsyncSession, Depends(get_session)]
Admin = Annotated[Principal, Depends(require_scope("admin"))]
MAX_URL_CHARS = 2048
EXAMPLE_OUT: dict[str, JsonValue] = {
    "id": "0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d6e",
    "url": "https://example.com/hooks/decision-engine",
    "events": ["decision.ready", "decision.made"],
    "enabled": True,
    "created_at": "2026-10-09T08:30:00Z",
}


class SubscriptionIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "url": "https://example.com/hooks/decision-engine",
                    "events": ["decision.ready", "decision.made"],
                    "secret": "change-me-to-a-long-random-string",
                }
            ]
        }
    )

    url: str = Field(max_length=MAX_URL_CHARS)
    events: list[str]
    secret: SecretStr


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [EXAMPLE_OUT]})

    id: uuid.UUID
    url: str
    events: list[str]
    enabled: bool
    created_at: datetime


class SubscriptionList(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"data": [EXAMPLE_OUT]}]})

    data: list[SubscriptionOut]


def _out(row: WebhookSubscription) -> SubscriptionOut:
    return SubscriptionOut(
        id=row.id, url=row.url, events=list(row.events), enabled=row.enabled,
        created_at=row.created_at,
    )  # fmt: skip


@router.get(
    "",
    response_model=SubscriptionList,
    summary="List webhook subscriptions",
    operation_id="list_subscriptions",
    responses={403: {"description": "API key lacks the admin scope"}},
)
async def list_subscriptions(principal: Admin, session: Session) -> SubscriptionList:
    rows = await service.list_subscriptions(session, tenant_id=principal.tenant_id)
    return SubscriptionList(data=[_out(r) for r in rows])


@router.post(
    "",
    response_model=SubscriptionOut,
    status_code=201,
    summary="Create a webhook subscription",
    operation_id="create_subscription",
    responses={
        403: {"description": "API key lacks the admin scope"},
        422: {"description": "Unsafe URL, unknown event, empty events or a short secret"},
    },
)
async def create_subscription(
    body: SubscriptionIn, principal: Admin, session: Session
) -> SubscriptionOut:
    try:
        row = await service.create_subscription(
            session,
            tenant_id=principal.tenant_id,
            url=body.url,
            events=body.events,
            secret=body.secret.get_secret_value(),
        )
    except service.InvalidSubscription as exc:
        raise ProblemError(422, "Invalid subscription", str(exc)) from exc
    await session.commit()
    return _out(row)


@router.delete(
    "/{subscription_id}",
    status_code=204,
    summary="Delete a webhook subscription",
    operation_id="delete_subscription",
    responses={
        403: {"description": "API key lacks the admin scope"},
        404: {"description": "No such subscription for this tenant"},
    },
)
async def delete_subscription(
    subscription_id: uuid.UUID, principal: Admin, session: Session
) -> Response:
    deleted = await service.delete_subscription(
        session, tenant_id=principal.tenant_id, subscription_id=subscription_id
    )
    if not deleted:
        raise ProblemError(404, "Not found", "No such subscription")
    await session.commit()
    return Response(status_code=204)
