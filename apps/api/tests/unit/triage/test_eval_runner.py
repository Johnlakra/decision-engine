"""Eval runner: metrics math, exit codes and fakes-driven runs (FR-73). No network."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.triage import fallback
from scripts import eval as ev
from tests.fakes.fake_laya import FakeLayaClient
from tests.fakes.fake_llm import FakeLLM

Q = {
    "keep": {
        "type": "choice",
        "instructions": "Keep?",
        "criteria": {"A": "yes", "B": "no"},
    }
}


def S(expected: str, predicted: str | None, conf: float | None, lang: str = "en") -> ev.Sample:
    return ev.Sample("keep", expected, predicted, conf, lang)


def test_accuracy_counts_only_answered_and_reports_coverage() -> None:
    samples = [S("A", "A", 0.9), S("A", "B", 0.8), S("B", None, None), S("B", "B", 0.7)]
    m = ev.summarize(samples)
    assert m["n"] == 4 and m["answered"] == 3
    assert m["accuracy"] == pytest.approx(2 / 3)
    assert m["coverage"] == pytest.approx(0.75)


def test_ece_ten_bins() -> None:
    # bin 9: conf 0.95 avg, acc 0.5 -> |0.5-0.95| * 2/4 ; bin 5: conf 0.55, acc 1 -> .45 * 2/4
    samples = [S("A", "A", 0.95), S("A", "B", 0.95), S("A", "A", 0.55), S("A", "A", 0.55)]
    assert ev.ece(samples) == pytest.approx(0.45)


def test_ece_perfectly_calibrated_and_empty() -> None:
    assert ev.ece([S("A", "A", 1.0)]) == pytest.approx(0.0)
    assert ev.ece([S("A", None, None)]) == 0.0


def test_confusion_matrix_and_language_slice() -> None:
    samples = [S("A", "A", 0.9), S("A", "B", 0.9, "hi"), S("B", "B", 0.9, "hi"), S("B", None, None)]
    conf = ev.confusion(samples)
    assert conf["keep"]["A"] == {"A": 1, "B": 1}
    assert conf["keep"]["B"] == {"B": 1, "none": 1}
    lang = ev.by_language(samples)
    assert lang["hi"]["accuracy"] == pytest.approx(0.5)
    assert lang["en"]["n"] == 2 and lang["en"]["accuracy"] == pytest.approx(1.0)


def write_eval(root: Path, rows: int = 2) -> Path:
    path = root / "x.jsonl"
    lines: list[dict[str, Any]] = [
        {
            "state": f"Row {i}",
            "questions": Q,
            "expected": {"keep": "A"},
            "tags": [],
            "language": "hi" if i else "en",
        }
        for i in range(rows)
    ]
    path.write_text("\n".join(json.dumps(r) for r in lines))
    return path


def test_exit_2_when_nothing_configured(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_eval(tmp_path)
    settings = Settings(laya_url="")
    code = ev.main(["--niche", "x", "--evals-dir", str(tmp_path)], settings=settings, has_llm=False)
    assert code == 2
    assert "skipped" in capsys.readouterr().out.lower()


def test_missing_file_is_exit_1(tmp_path: Path) -> None:
    code = ev.main(
        ["--niche", "nope", "--evals-dir", str(tmp_path)], settings=Settings(), has_llm=True
    )
    assert code == 1


async def test_run_with_fakes_and_limit(fake_llm: FakeLLM, tmp_path: Path) -> None:
    rows = ev.load_rows(write_eval(tmp_path, rows=3), limit=2)
    assert len(rows) == 2
    laya = FakeLayaClient()  # confidently answers first key "A"
    fake_llm.script("classify", {"keep": {"choice": "B", "confidence": 0.6}}, repeat=True)

    async def classify(state: str, questions: dict[str, Any], language: str) -> Any:
        return await fallback.classify(state, questions, sensitivity="public", language=language)

    results = await ev.run_eval(rows, laya=laya, classify=classify)
    assert ev.summarize(results["laya"])["accuracy"] == 1.0
    assert ev.summarize(results["llm"])["accuracy"] == 0.0
    assert len(fake_llm.calls_for("classify")) == 2
    assert all(c.sensitivity == "public" for c in fake_llm.calls)
    assert "Row 0" in json.dumps(fake_llm.calls[0].messages)


async def test_llm_failures_become_abstentions_and_stop_early(
    fake_llm: FakeLLM, tmp_path: Path
) -> None:
    rows = ev.load_rows(write_eval(tmp_path, rows=ev.MAX_LLM_FAILURES + 3))

    async def classify(state: str, questions: dict[str, Any], language: str) -> Any:
        raise fallback.FallbackUnavailable("x")

    results = await ev.run_eval(rows, laya=None, classify=classify)
    assert "laya" not in results
    assert ev.summarize(results["llm"])["answered"] == 0
    assert len(results["llm"]) == len(rows)


def test_main_prints_json_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    write_eval(tmp_path)
    laya = FakeLayaClient()
    code = ev.main(
        ["--niche", "x", "--evals-dir", str(tmp_path)],
        settings=Settings(laya_url="http://laya"),
        has_llm=False,
        laya=laya,
    )
    assert code == 0
    out = capsys.readouterr().out
    report = json.loads(out[out.index("{") :])
    assert report["niche"] == "x"
    assert set(report["systems"]) == {"laya"}
    sys_ = report["systems"]["laya"]
    assert {"accuracy", "ece", "confusion", "by_language", "coverage"} <= set(sys_)
    assert "Row 0" not in out
