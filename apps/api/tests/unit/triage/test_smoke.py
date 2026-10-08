"""python -m app.triage.smoke: exit 0 ok, 1 fail, 2 skipped; never prints the key (FR-20, A7)."""

import httpx
import pytest
import respx

from app.core.config import get_settings
from app.triage import smoke

SECRET = "laya-secret-key-xyz"
URL = "http://laya.test"


@pytest.fixture
def laya_env(settings_env: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    settings_env.setenv("LAYA_URL", URL)
    settings_env.setenv("LAYA_API_KEY", SECRET)
    settings_env.setenv("LAYA_MODE", "shadow")
    get_settings.cache_clear()
    return settings_env


def test_skipped_exit_2_when_laya_url_empty(
    settings_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings_env.setenv("LAYA_URL", "")
    get_settings.cache_clear()
    with pytest.raises(SystemExit) as exit_info:
        smoke.main()
    assert exit_info.value.code == 2
    assert "skipped" in capsys.readouterr().out


@respx.mock
def test_ok_exit_0_prints_probabilities_and_never_the_key(
    laya_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def reply(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {SECRET}"
        answer = {
            "type": "choice",
            "choice": "A",
            "confidence": 0.9,
            "probabilities": {"A": 0.9, "B": 0.1},
        }
        result = {"model": "laya-rl-agent", "usage": {}, "answers": {"needs_decision": answer}}
        return httpx.Response(200, json={"results": [result]})

    respx.post(url__startswith=URL).mock(side_effect=reply)
    with pytest.raises(SystemExit) as exit_info:
        smoke.main()
    out = capsys.readouterr()
    assert exit_info.value.code == 0
    assert "needs_decision[A] = 0.9000" in out.out and "needs_decision[B] = 0.1000" in out.out
    assert SECRET not in out.out and SECRET not in out.err


@respx.mock
def test_fail_exit_1_when_laya_returns_garbage(
    laya_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    respx.post(url__startswith=URL).mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(SystemExit) as exit_info:
        smoke.main()
    assert exit_info.value.code == 1
    out = capsys.readouterr().out
    assert "fail" in out and SECRET not in out


@respx.mock
def test_fail_exit_1_on_connection_error(laya_env: pytest.MonkeyPatch) -> None:
    respx.post(url__startswith=URL).mock(side_effect=httpx.ConnectError("refused"))
    assert smoke.asyncio.run(smoke.run()) == 1
