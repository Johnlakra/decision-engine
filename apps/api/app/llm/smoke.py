"""`python -m app.llm.smoke [--provider gemini]`: tiny real call. Exit 0 ok, 1 fail, 2 skipped."""

import argparse
import asyncio
import sys
from typing import Literal

from pydantic import BaseModel

from app.llm import gateway
from app.llm.config import ProviderConfig, load_config
from app.llm.errors import LLMUnavailable

EXIT_OK, EXIT_FAIL, EXIT_SKIPPED = 0, 1, 2
DEFAULT_PROVIDER = "gemini"


class SmokeAnswer(BaseModel):
    answer: Literal["yes", "no"]
    reason: str


PROMPT = [
    {"role": "user", "content": "Is the sky blue on a clear day? Answer yes or no with a reason."}
]


def _key_name(provider: ProviderConfig) -> str:
    return (
        f"{provider.name.upper()}_API_KEY" if provider.needs_key else f"{provider.name.upper()}_URL"
    )


def _targets(requested: str | None) -> list[ProviderConfig]:
    providers = load_config().providers
    if requested:
        return [providers[requested]] if requested in providers else []
    configured = [p for p in providers.values() if p.available]
    return configured or [providers[DEFAULT_PROVIDER]]


async def _run_one(provider: ProviderConfig) -> int:
    if not provider.available:
        print(f"SKIPPED: {_key_name(provider)} not set")
        return EXIT_SKIPPED
    try:
        answer = await gateway.complete_json_on(provider.name, SmokeAnswer, PROMPT)
    except LLMUnavailable as exc:
        print(f"FAIL {provider.name} ({provider.litellm_model}): {exc}")
        return EXIT_FAIL
    print(f"OK {provider.name} ({provider.litellm_model}): {answer.model_dump_json()}")
    return EXIT_OK


async def _main(requested: str | None) -> int:
    targets = _targets(requested)
    if not targets:
        print(f"FAIL: unknown provider {requested!r}")
        return EXIT_FAIL
    codes = [await _run_one(p) for p in targets]
    if EXIT_FAIL in codes:
        return EXIT_FAIL
    return EXIT_OK if EXIT_OK in codes else EXIT_SKIPPED


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tiny real-provider LLM smoke test.")
    parser.add_argument("--provider", help="gemini, groq, cerebras, openrouter, ollama, openai")
    args = parser.parse_args(argv)
    return asyncio.run(_main(args.provider))


if __name__ == "__main__":
    sys.exit(main())
