"""Eval runner: Laya and the LLM fallback on evals/<niche>.jsonl (FR-73).

    cd apps/api && uv run python -m scripts.eval --niche generic [--limit N]

Exit codes: 0 report printed, 1 bad input, 2 skipped (no LAYA_URL and no LLM key).
Row text is untrusted: it only reaches a prompt through `fallback.classify`, which fences it.
Bodies are never printed or logged; the report holds counts and ratios only.
"""

import argparse
import asyncio
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.llm.config import load_config
from app.schemas.triage import Answer
from app.triage import fallback
from app.triage.answers import parse_laya_result
from app.triage.laya_client import HttpLayaClient, LayaClient

EXIT_OK, EXIT_BAD_INPUT, EXIT_SKIPPED = 0, 1, 2
ECE_BINS = 10
MAX_LLM_FAILURES = 5  # stop spending budget when the LLM is clearly unavailable
NO_ANSWER = "none"
DEFAULT_EVALS_DIR = Path(__file__).resolve().parents[3] / "evals"

Classify = Callable[[str, dict[str, Any], str], Awaitable[dict[str, Answer]]]


@dataclass(frozen=True)
class Sample:
    qid: str
    expected: str
    predicted: str | None  # None = no opinion
    confidence: float | None
    language: str


def load_rows(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
        if limit is not None and len(rows) >= limit:
            break
    return rows


def _label(answer: Answer) -> str | None:
    if answer.type == "choice":
        return answer.choice
    if answer.type == "score" and answer.level is not None:
        return str(answer.level)
    return None  # noul answers are not evaluated against a label


def _confidence(answer: Answer) -> float | None:
    if answer.confidence is not None:
        return answer.confidence
    return max(answer.probabilities.values()) if answer.probabilities else None


def _samples_for(row: dict[str, Any], answers: dict[str, Answer]) -> list[Sample]:
    language = str(row.get("language") or "en")
    out: list[Sample] = []
    for qid, expected in row.get("expected", {}).items():
        answer = answers.get(qid)
        label = _label(answer) if answer else None
        conf = _confidence(answer) if answer and label is not None else None
        out.append(Sample(qid, str(expected), label, conf, language))
    return out


async def run_eval(
    rows: Sequence[dict[str, Any]],
    *,
    laya: LayaClient | None,
    classify: Classify | None,
) -> dict[str, list[Sample]]:
    results: dict[str, list[Sample]] = {}
    if laya is not None:
        laya_samples: list[Sample] = []
        for row in rows:
            raw = await laya.batch([row["state"]], row["questions"])
            answers = parse_laya_result(row["questions"], raw[0] if raw else None)
            laya_samples += _samples_for(row, answers)
        results["laya"] = laya_samples
    if classify is not None:
        llm_samples: list[Sample] = []
        failures = 0
        for row in rows:
            llm_answers: dict[str, Answer] = {}
            if failures < MAX_LLM_FAILURES:
                try:
                    llm_answers = await classify(
                        row["state"], row["questions"], str(row.get("language") or "en")
                    )
                except fallback.FallbackUnavailable:
                    failures += 1
            llm_samples += _samples_for(row, llm_answers)
        results["llm"] = llm_samples
    return results


def _answered(samples: Sequence[Sample]) -> list[Sample]:
    return [s for s in samples if s.predicted is not None]


def _accuracy(samples: Sequence[Sample]) -> float | None:
    answered = _answered(samples)
    return sum(s.predicted == s.expected for s in answered) / len(answered) if answered else None


def ece(samples: Sequence[Sample], bins: int = ECE_BINS) -> float:
    """Expected calibration error over answered samples with a confidence."""
    scored = [s for s in _answered(samples) if s.confidence is not None]
    if not scored:
        return 0.0
    buckets: dict[int, list[Sample]] = defaultdict(list)
    for s in scored:
        conf = min(max(s.confidence or 0.0, 0.0), 1.0)
        buckets[min(int(conf * bins), bins - 1)].append(s)
    total = 0.0
    for members in buckets.values():
        acc = sum(m.predicted == m.expected for m in members) / len(members)
        avg_conf = sum(m.confidence or 0.0 for m in members) / len(members)
        total += len(members) / len(scored) * abs(acc - avg_conf)
    return total


def confusion(samples: Sequence[Sample]) -> dict[str, dict[str, dict[str, int]]]:
    """question -> expected -> predicted ('none' = no opinion) -> count."""
    out: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    for s in samples:
        out[s.qid][s.expected][s.predicted or NO_ANSWER] += 1
    return {q: {e: dict(c) for e, c in rows.items()} for q, rows in out.items()}


def by_language(samples: Sequence[Sample]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[Sample]] = defaultdict(list)
    for s in samples:
        groups[s.language].append(s)
    return {
        lang: {"n": len(g), "answered": len(_answered(g)), "accuracy": _accuracy(g)}
        for lang, g in sorted(groups.items())
    }


def summarize(samples: Sequence[Sample]) -> dict[str, Any]:
    answered = _answered(samples)
    return {
        "n": len(samples),
        "answered": len(answered),
        "coverage": len(answered) / len(samples) if samples else 0.0,
        "accuracy": _accuracy(samples),
        "ece": ece(samples),
        "confusion": confusion(samples),
        "by_language": by_language(samples),
    }


def llm_configured() -> bool:
    return any(p.available for p in load_config().providers.values())


async def _classify(state: str, questions: dict[str, Any], language: str) -> dict[str, Answer]:
    # Eval fixtures are synthetic, so "public" routing is right and keeps cloud budgets usable.
    return await fallback.classify(state, questions, sensitivity="public", language=language)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scripts.eval", description=__doc__)
    p.add_argument("--niche", required=True)
    p.add_argument("--limit", type=int, default=None, help="max rows (protects free-tier budgets)")
    p.add_argument("--evals-dir", type=Path, default=DEFAULT_EVALS_DIR)
    return p


def main(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    has_llm: bool | None = None,
    laya: LayaClient | None = None,
) -> int:
    args = _parser().parse_args(argv)
    settings = settings or get_settings()
    use_llm = llm_configured() if has_llm is None else has_llm
    http_laya = None if laya else HttpLayaClient.from_settings(settings)
    client: LayaClient | None = laya or http_laya
    if client is None and not use_llm:
        print("eval skipped: set LAYA_URL and/or an LLM provider key")  # noqa: T201
        return EXIT_SKIPPED
    path = args.evals_dir / f"{args.niche}.jsonl"
    if not path.is_file():
        print(f"eval file not found: {path}", file=sys.stderr)  # noqa: T201
        return EXIT_BAD_INPUT
    rows = load_rows(path, args.limit)
    results = asyncio.run(_run(rows, client, http_laya, use_llm))
    report = {"niche": args.niche, "rows": len(rows)} | {
        "systems": {name: summarize(s) for name, s in results.items()}
    }
    print(json.dumps(report, indent=2))  # noqa: T201
    return EXIT_OK


async def _run(
    rows: list[dict[str, Any]],
    client: LayaClient | None,
    http_laya: HttpLayaClient | None,
    use_llm: bool,
) -> dict[str, list[Sample]]:
    try:
        return await run_eval(rows, laya=client, classify=_classify if use_llm else None)
    finally:
        if http_laya is not None:
            await http_laya.aclose()


if __name__ == "__main__":
    raise SystemExit(main())
