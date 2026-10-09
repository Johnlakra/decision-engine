from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.decision_item_out import DecisionItemOut
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    item_id: UUID,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/items/{item_id}".format(
            item_id=quote(str(item_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | DecisionItemOut | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = DecisionItemOut.from_dict(response.json())

        return response_200

    if response.status_code == 404:
        response_404 = cast(Any, None)
        return response_404

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | DecisionItemOut | HTTPValidationError]:
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
) -> Response[Any | DecisionItemOut | HTTPValidationError]:
    """Get one item

    Args:
        item_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | DecisionItemOut | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    item_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Any | DecisionItemOut | HTTPValidationError | None:
    """Get one item

    Args:
        item_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | DecisionItemOut | HTTPValidationError
    """

    return sync_detailed(
        item_id=item_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    item_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any | DecisionItemOut | HTTPValidationError]:
    """Get one item

    Args:
        item_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | DecisionItemOut | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    item_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Any | DecisionItemOut | HTTPValidationError | None:
    """Get one item

    Args:
        item_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | DecisionItemOut | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            item_id=item_id,
            client=client,
        )
    ).parsed
