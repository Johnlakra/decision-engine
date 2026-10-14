from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.source_out import SourceOut
from ...models.source_patch import SourcePatch
from ...types import Response


def _get_kwargs(
    source_id: UUID,
    *,
    body: SourcePatch,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/v1/sources/{source_id}".format(
            source_id=quote(str(source_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | SourceOut | None:
    if response.status_code == 200:
        response_200 = SourceOut.from_dict(response.json())

        return response_200

    if response.status_code == 403:
        response_403 = cast(Any, None)
        return response_403

    if response.status_code == 404:
        response_404 = cast(Any, None)
        return response_404

    if response.status_code == 422:
        response_422 = cast(Any, None)
        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Any | SourceOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    source_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: SourcePatch,
) -> Response[Any | SourceOut]:
    """Enable or disable a source

    Args:
        source_id (UUID):
        body (SourcePatch): Only ``enabled`` can change (ADR 0010); any other key is a 422.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | SourceOut]
    """

    kwargs = _get_kwargs(
        source_id=source_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    source_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: SourcePatch,
) -> Any | SourceOut | None:
    """Enable or disable a source

    Args:
        source_id (UUID):
        body (SourcePatch): Only ``enabled`` can change (ADR 0010); any other key is a 422.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | SourceOut
    """

    return sync_detailed(
        source_id=source_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    source_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: SourcePatch,
) -> Response[Any | SourceOut]:
    """Enable or disable a source

    Args:
        source_id (UUID):
        body (SourcePatch): Only ``enabled`` can change (ADR 0010); any other key is a 422.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | SourceOut]
    """

    kwargs = _get_kwargs(
        source_id=source_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    source_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    body: SourcePatch,
) -> Any | SourceOut | None:
    """Enable or disable a source

    Args:
        source_id (UUID):
        body (SourcePatch): Only ``enabled`` can change (ADR 0010); any other key is a 422.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | SourceOut
    """

    return (
        await asyncio_detailed(
            source_id=source_id,
            client=client,
            body=body,
        )
    ).parsed
