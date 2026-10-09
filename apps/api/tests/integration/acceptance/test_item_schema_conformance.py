"""GET /v1/items/{id} output conforms to schemas/decision_item.schema.json (FR-10, FR-13, FR-06)."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

pytest.importorskip("app.graph.run")

from tests.fakes.fake_laya import FakeLayaClient  # noqa: E402

from ._pipeline import auth, post_item, run_worker_until_idle  # noqa: E402
from ._scripts import SCHOOL_ERP_BRIEF  # noqa: E402

pytestmark = pytest.mark.integration
SCHEMA = json.loads(
    (Path(__file__).resolve().parents[5] / "schemas" / "decision_item.schema.json").read_text()
)
PUNJABI = "ਸਾਨੂੰ ਸਕੂਲ ਲਈ ਇੱਕ ਐਪ ਚਾਹੀਦੀ ਹੈ ਜੋ ਬਿਨਾਂ ਇੰਟਰਨੈੱਟ ਦੇ ਚੱਲੇ"


async def _get(client, key: str, item_id: str) -> dict:  # type: ignore[no-untyped-def,type-arg]
    response = await client.get(f"/v1/items/{item_id}", headers=auth(key))
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def _without_null_content(body: dict) -> dict:  # type: ignore[type-arg]
    content = {k: v for k, v in body["content"].items() if v is not None}
    return {**body, "content": content}


@pytest.mark.xfail(
    strict=True,
    reason="BUG: API emits content.summary/sender/url as null but schemas/decision_item.schema.json"
    ":24-26 types them 'string' (NormalisedContent app/schemas/content.py:13-15 is str | None)",
)
async def test_api_output_validates_as_is_against_the_published_schema(
    client, account, factory, llm, use_laya
) -> None:  # type: ignore[no-untyped-def]
    use_laya(FakeLayaClient())
    item_id = await post_item(client, account.key, text=SCHOOL_ERP_BRIEF, source_ref="schema0")
    await run_worker_until_idle(factory)

    Draft202012Validator(SCHEMA).validate(await _get(client, account.key, item_id))


async def test_processed_item_validates_against_the_published_schema_ignoring_nulls(
    client, account, factory, llm, use_laya
) -> None:  # type: ignore[no-untyped-def]
    use_laya(FakeLayaClient())
    item_id = await post_item(client, account.key, text=SCHOOL_ERP_BRIEF, source_ref="schema1")
    await run_worker_until_idle(factory)

    body = await _get(client, account.key, item_id)

    Draft202012Validator(SCHEMA).validate(_without_null_content(body))
    assert body["content"]["title"] and body["language"]
    assert not {"raw", "hints", "callback_url"} & set(body)


async def test_punjabi_item_is_detected_and_still_conforms(
    client, account, factory, llm, use_laya
) -> None:  # type: ignore[no-untyped-def]
    use_laya(FakeLayaClient())
    item_id = await post_item(client, account.key, text=PUNJABI, source_ref="schema2")
    await run_worker_until_idle(factory)

    body = await _get(client, account.key, item_id)

    Draft202012Validator(SCHEMA).validate(_without_null_content(body))
    assert body["language"] == "pa"
