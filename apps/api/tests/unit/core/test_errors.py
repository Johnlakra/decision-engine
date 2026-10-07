"""problem+json tests (NFR-08)."""

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from app.core.errors import ProblemError, install_problem_handlers


class Body(BaseModel):
    n: int


@pytest.fixture
def client() -> httpx.AsyncClient:
    app = FastAPI()
    install_problem_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise ProblemError(404, "Not found", "No such item", errors=[{"field": "id"}])

    @app.post("/body")
    async def body(b: Body) -> Body:
        return b

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_problem_shape(client: httpx.AsyncClient) -> None:
    r = await client.get("/boom")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json() == {
        "type": "about:blank",
        "title": "Not found",
        "status": 404,
        "detail": "No such item",
        "instance": "/boom",
        "errors": [{"field": "id"}],
    }


async def test_validation_is_422_problem(client: httpx.AsyncClient) -> None:
    r = await client.post("/body", json={"n": "x"})
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    data = r.json()
    assert data["status"] == 422 and data["errors"] and "input" not in data["errors"][0]


async def test_unknown_route_is_problem(client: httpx.AsyncClient) -> None:
    r = await client.get("/nope")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
