"""OpenAPI quality gate: every operation has tags and an example (generates the SDKs)."""

from typing import Any

import pytest

from app.main import create_app

HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def _operations() -> list[tuple[str, str, dict[str, Any]]]:
    spec = create_app().openapi()
    return [
        (method.upper(), path, op)
        for path, item in spec["paths"].items()
        for method, op in item.items()
        if method in HTTP_METHODS
    ]


def _resolve(spec: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if ref is None:
        return schema
    node: Any = spec
    for part in ref.removeprefix("#/").split("/"):
        node = node[part]
    return node  # type: ignore[no-any-return]


def _has_example(spec: dict[str, Any], content: dict[str, Any]) -> bool:
    for media in content.values():
        if "example" in media or "examples" in media:
            return True
        schema = _resolve(spec, media.get("schema", {}))
        if schema.get("examples") or "example" in schema:
            return True
    return False


def _success_has_example(spec: dict[str, Any], op: dict[str, Any]) -> bool:
    for code, response in op["responses"].items():
        if not code.startswith("2"):
            continue
        content = response.get("content")
        if content is None:  # 204: nothing to exemplify
            return True
        if _has_example(spec, content):
            return True
    return False


OPS = _operations()
SPEC = create_app().openapi()


def test_there_are_routes() -> None:
    assert len(OPS) >= 10


@pytest.mark.parametrize(("method", "path", "op"), OPS, ids=[f"{m} {p}" for m, p, _ in OPS])
def test_operation_has_tags_summary_and_example(method: str, path: str, op: dict[str, Any]) -> None:
    assert op.get("tags"), f"{method} {path} has no tags"
    assert op.get("summary"), f"{method} {path} has no summary"
    assert op.get("operationId"), f"{method} {path} has no operationId"
    assert _success_has_example(SPEC, op), f"{method} {path} has no example in a 2xx response"
