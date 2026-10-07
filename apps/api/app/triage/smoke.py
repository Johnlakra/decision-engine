"""`python -m app.triage.smoke`: one state, `needs_decision`. Exit 0 ok, 1 fail, 2 skipped."""

import asyncio
import sys

from app.core.config import get_settings
from app.triage.laya_client import HttpLayaClient

EXIT_OK, EXIT_FAIL, EXIT_SKIPPED = 0, 1, 2
STATE = (
    "Subject: Invoice overdue\nFrom: billing@example.com\n\nPlease pay by Friday or service stops."
)
QUESTIONS = {
    "needs_decision": {
        "type": "choice",
        "instructions": "Does this require the owner to decide or act?",
        "criteria": {"A": "yes, a decision or action is needed", "B": "no, informational only"},
    }
}


async def run() -> int:
    client = HttpLayaClient.from_settings(get_settings())
    if client is None:
        print("skipped: LAYA_URL is empty")
        return EXIT_SKIPPED
    try:
        result = (await client.batch([STATE], QUESTIONS))[0]
    finally:
        await client.aclose()
    if result is None:
        print("fail: no usable answer from laya")
        return EXIT_FAIL
    answer = result["answers"]["needs_decision"]
    print(f"model={result['model']} latency_ms={result['latency_ms']} choice={answer['choice']}")
    for key, prob in answer["probabilities"].items():
        print(f"  needs_decision[{key}] = {prob:.4f}")
    return EXIT_OK


def main() -> None:
    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    main()
