import datetime
from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.export_feedback_format import ExportFeedbackFormat
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    niche: None | str | Unset = UNSET,
    format_: ExportFeedbackFormat | Unset = "laya_train",
    since: datetime.datetime | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_niche: None | str | Unset
    if isinstance(niche, Unset):
        json_niche = UNSET
    else:
        json_niche = niche
    params["niche"] = json_niche

    json_format_: str | Unset = UNSET
    if not isinstance(format_, Unset):
        json_format_ = format_

    params["format"] = json_format_

    json_since: None | str | Unset
    if isinstance(since, Unset):
        json_since = UNSET
    elif isinstance(since, datetime.datetime):
        json_since = since.isoformat()
    else:
        json_since = since
    params["since"] = json_since

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/feedback/export",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 403:
        response_403 = cast(Any, None)
        return response_403

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    niche: None | str | Unset = UNSET,
    format_: ExportFeedbackFormat | Unset = "laya_train",
    since: datetime.datetime | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Export human decisions as JSONL

    Args:
        niche (None | str | Unset):
        format_ (ExportFeedbackFormat | Unset):  Default: 'laya_train'.
        since (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        niche=niche,
        format_=format_,
        since=since,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    niche: None | str | Unset = UNSET,
    format_: ExportFeedbackFormat | Unset = "laya_train",
    since: datetime.datetime | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Export human decisions as JSONL

    Args:
        niche (None | str | Unset):
        format_ (ExportFeedbackFormat | Unset):  Default: 'laya_train'.
        since (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        niche=niche,
        format_=format_,
        since=since,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    niche: None | str | Unset = UNSET,
    format_: ExportFeedbackFormat | Unset = "laya_train",
    since: datetime.datetime | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Export human decisions as JSONL

    Args:
        niche (None | str | Unset):
        format_ (ExportFeedbackFormat | Unset):  Default: 'laya_train'.
        since (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        niche=niche,
        format_=format_,
        since=since,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    niche: None | str | Unset = UNSET,
    format_: ExportFeedbackFormat | Unset = "laya_train",
    since: datetime.datetime | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Export human decisions as JSONL

    Args:
        niche (None | str | Unset):
        format_ (ExportFeedbackFormat | Unset):  Default: 'laya_train'.
        since (datetime.datetime | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            niche=niche,
            format_=format_,
            since=since,
        )
    ).parsed
