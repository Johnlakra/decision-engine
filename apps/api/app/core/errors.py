"""RFC 9457 problem+json errors (NFR-08)."""

from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_JSON = "application/problem+json"


class ProblemError(Exception):
    def __init__(
        self,
        status: int,
        title: str,
        detail: str,
        type: str = "about:blank",  # noqa: A002
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(f"{status} {title}: {detail}")
        self.status = status
        self.title = title
        self.detail = detail
        self.type = type
        self.errors = errors


def _response(
    request: Request, exc: ProblemError, headers: dict[str, str] | None = None
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": exc.type,
        "title": exc.title,
        "status": exc.status,
        "detail": exc.detail,
        "instance": request.url.path,
    }
    if exc.errors is not None:
        body["errors"] = exc.errors
    return JSONResponse(body, status_code=exc.status, media_type=PROBLEM_JSON, headers=headers)


def install_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem(request: Request, exc: Exception) -> JSONResponse:
        exc = cast("ProblemError", exc)
        return _response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: Exception) -> JSONResponse:
        exc = cast("RequestValidationError", exc)
        errors = [
            {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"], "code": e["type"]}
            for e in exc.errors()
        ]
        problem = ProblemError(422, "Validation failed", "Request validation failed", errors=errors)
        return _response(request, problem)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: Exception) -> JSONResponse:
        exc = cast("StarletteHTTPException", exc)
        problem = ProblemError(exc.status_code, _title(exc.status_code), str(exc.detail))
        return _response(request, problem, dict(exc.headers or {}))


def _title(status: int) -> str:
    from http import HTTPStatus

    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"
