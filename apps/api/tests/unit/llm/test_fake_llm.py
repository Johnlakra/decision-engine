"""The FakeLLM double other test suites rely on."""

import pytest
from pydantic import BaseModel

from app.llm import gateway
from app.llm.errors import LLMUnavailable, NoPrivateProvider
from tests.fakes.fake_llm import Failure, FakeLLM


class Out(BaseModel):
    n: int


async def test_scripted_responses_in_order_and_recorded(fake_llm: FakeLLM) -> None:
    fake_llm.script("classify", Out(n=1), {"n": 2}, '{"n": 3}')
    got = [
        (await gateway.complete_json("classify", Out, [], sensitivity="public", item_id="i")).n
        for _ in range(3)
    ]
    assert got == [1, 2, 3]
    assert len(fake_llm.calls_for("classify")) == 3 and fake_llm.calls[0].item_id == "i"


@pytest.mark.parametrize("mode", list(Failure))
async def test_simulated_failures_raise_llm_unavailable(fake_llm: FakeLLM, mode: Failure) -> None:
    fake_llm.script("decide", mode)
    with pytest.raises(LLMUnavailable):
        await gateway.complete_json("decide", Out, [], sensitivity="public")


async def test_private_unavailable_and_text(fake_llm: FakeLLM) -> None:
    fake_llm.private_available = False
    with pytest.raises(NoPrivateProvider):
        await gateway.complete_text("draft", [], sensitivity="private")
    fake_llm.private_available = True
    fake_llm.script("draft", "hello", repeat=True)
    assert await gateway.complete_text("draft", [], sensitivity="private") == "hello"
    assert await gateway.complete_text("draft", [], sensitivity="private") == "hello"


async def test_unscripted_purpose_is_unavailable(fake_llm: FakeLLM) -> None:
    with pytest.raises(LLMUnavailable):
        await gateway.complete_text("draft", [], sensitivity="public")
