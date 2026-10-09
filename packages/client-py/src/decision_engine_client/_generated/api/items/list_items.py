from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.item_page import ItemPage
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    status: None | str | Unset = UNSET,
    niche: None | str | Unset = UNSET,
    source: None | str | Unset = UNSET,
    q: None | str | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_status: None | str | Unset
    if isinstance(status, Unset):
        json_status = UNSET
    else:
        json_status = status
    params["status"] = json_status

    json_niche: None | str | Unset
    if isinstance(niche, Unset):
        json_niche = UNSET
    else:
        json_niche = niche
    params["niche"] = json_niche

    json_source: None | str | Unset
    if isinstance(source, Unset):
        json_source = UNSET
    else:
        json_source = source
    params["source"] = json_source

    json_q: None | str | Unset
    if isinstance(q, Unset):
        json_q = UNSET
    else:
        json_q = q
    params["q"] = json_q

    json_cursor: None | str | Unset
    if isinstance(cursor, Unset):
        json_cursor = UNSET
    else:
        json_cursor = cursor
    params["cursor"] = json_cursor

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/items",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ItemPage | None:
    if response.status_code == 200:
        response_200 = ItemPage.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | ItemPage]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    status: None | str | Unset = UNSET,
    niche: None | str | Unset = UNSET,
    source: None | str | Unset = UNSET,
    q: None | str | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,
) -> Response[HTTPValidationError | ItemPage]:
    """List items

     Newest first. `cursor` is the `next_cursor` of the previous page.

    Args:
        status (None | str | Unset):
        niche (None | str | Unset):
        source (None | str | Unset):
        q (None | str | Unset):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ItemPage]
    """

    kwargs = _get_kwargs(
        status=status,
        niche=niche,
        source=source,
        q=q,
        cursor=cursor,
        limit=limit,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    status: None | str | Unset = UNSET,
    niche: None | str | Unset = UNSET,
    source: None | str | Unset = UNSET,
    q: None | str | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,
) -> HTTPValidationError | ItemPage | None:
    """List items

     Newest first. `cursor` is the `next_cursor` of the previous page.

    Args:
        status (None | str | Unset):
        niche (None | str | Unset):
        source (None | str | Unset):
        q (None | str | Unset):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ItemPage
    """

    return sync_detailed(
        client=client,
        status=status,
        niche=niche,
        source=source,
        q=q,
        cursor=cursor,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    status: None | str | Unset = UNSET,
    niche: None | str | Unset = UNSET,
    source: None | str | Unset = UNSET,
    q: None | str | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,
) -> Response[HTTPValidationError | ItemPage]:
    """List items

     Newest first. `cursor` is the `next_cursor` of the previous page.

    Args:
        status (None | str | Unset):
        niche (None | str | Unset):
        source (None | str | Unset):
        q (None | str | Unset):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ItemPage]
    """

    kwargs = _get_kwargs(
        status=status,
        niche=niche,
        source=source,
        q=q,
        cursor=cursor,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    status: None | str | Unset = UNSET,
    niche: None | str | Unset = UNSET,
    source: None | str | Unset = UNSET,
    q: None | str | Unset = UNSET,
    cursor: None | str | Unset = UNSET,
    limit: int | Unset = 50,
) -> HTTPValidationError | ItemPage | None:
    """List items

     Newest first. `cursor` is the `next_cursor` of the previous page.

    Args:
        status (None | str | Unset):
        niche (None | str | Unset):
        source (None | str | Unset):
        q (None | str | Unset):
        cursor (None | str | Unset):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ItemPage
    """

    return (
        await asyncio_detailed(
            client=client,
            status=status,
            niche=niche,
            source=source,
            q=q,
            cursor=cursor,
            limit=limit,
        )
    ).parsed
