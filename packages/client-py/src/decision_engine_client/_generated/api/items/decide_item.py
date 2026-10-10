from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.decision_in import DecisionIn
from ...models.decision_result import DecisionResult
from ...types import Response


def _get_kwargs(
    item_id: UUID,
    *,
    body: DecisionIn,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/items/{item_id}/decision".format(
            item_id=quote(str(item_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | DecisionResult | None:
    if response.status_code == 200:
        response_200 = DecisionResult.from_dict(response.json())

        return response_200

    if response.status_code == 404:
        response_404 = cast(Any, None)
        return response_404

    if response.status_code == 409:
        response_409 = cast(Any, None)
        return response_409

    if response.status_code == 422:
        response_422 = cast(Any, None)
        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | DecisionResult]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    item_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: DecisionIn,
) -> Response[Any | DecisionResult]:
    """Approve, reject, edit or snooze a waiting decision

    Args:
        item_id (UUID):
        body (DecisionIn): Body of ``POST /v1/items/{id}/decision`` (API.md).

            The "snooze_until is in the future" rule is an API-layer check (``api/v1/decisions.py``):
            the
            graph re-validates this model on a resume replay, long after the time may have passed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | DecisionResult]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    item_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: DecisionIn,
) -> Any | DecisionResult | None:
    """Approve, reject, edit or snooze a waiting decision

    Args:
        item_id (UUID):
        body (DecisionIn): Body of ``POST /v1/items/{id}/decision`` (API.md).

            The "snooze_until is in the future" rule is an API-layer check (``api/v1/decisions.py``):
            the
            graph re-validates this model on a resume replay, long after the time may have passed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | DecisionResult
    """

    return sync_detailed(
        item_id=item_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    item_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: DecisionIn,
) -> Response[Any | DecisionResult]:
    """Approve, reject, edit or snooze a waiting decision

    Args:
        item_id (UUID):
        body (DecisionIn): Body of ``POST /v1/items/{id}/decision`` (API.md).

            The "snooze_until is in the future" rule is an API-layer check (``api/v1/decisions.py``):
            the
            graph re-validates this model on a resume replay, long after the time may have passed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | DecisionResult]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    item_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: DecisionIn,
) -> Any | DecisionResult | None:
    """Approve, reject, edit or snooze a waiting decision

    Args:
        item_id (UUID):
        body (DecisionIn): Body of ``POST /v1/items/{id}/decision`` (API.md).

            The "snooze_until is in the future" rule is an API-layer check (``api/v1/decisions.py``):
            the
            graph re-validates this model on a resume replay, long after the time may have passed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | DecisionResult
    """

    return (
        await asyncio_detailed(
            item_id=item_id,
            client=client,
            body=body,
        )
    ).parsed
