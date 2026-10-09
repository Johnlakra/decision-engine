"""Live Phase 1 acceptance (L1-L3) against a running API (`make dev`, then `make accept-phase1`).

L1: POST the school-ERP brief, poll up to 120 s, expect ``awaiting_approval`` / ``tech_stack`` /
>= 2 options. L2 (``--webhook-url``): subscribe, then approve, so
scripts.webhook_receiver prints ``signature OK``. L3 (``--expect-laya-down``): also require
``triage.shadow.error=laya_unavailable``.

Skip rule: if an LLM key, TOKEN_ENC_KEY, WEBHOOK_ALLOW_PRIVATE_URLS=true or DE_API_KEY is missing
the runner prints ``skipped: missing ...`` and exits 0 (recorded as pending, not passed). Presence
is checked through ``app.core.config``; no value is ever printed. Exit 1 means a check failed.
"""

import argparse
import os
import sys
import time
import uuid
from collections.abc import Sequence
from typing import Any

import httpx

from app.core.config import get_settings

BRIEF = (
    "We are a 3-person team building a school ERP (fees, attendance, report cards) for 12 "
    "government-aided schools in Punjab. Budget is Rs 0 to start. Schools have patchy internet, "
    "so it must work offline. Teachers use cheap Android phones. Which stack should we use?"
)
POLL_TIMEOUT_S = 120
POLL_INTERVAL_S = 2.0
MIN_OPTIONS = 2
TERMINAL_BAD = {"failed", "needs_human_triage", "discarded", "informational"}
API_KEY_ENV = "DE_API_KEY"
DEFAULT_SUBSCRIPTION_SECRET = "s3cr3t"  # noqa: S105 - dev demo secret matching the plan


def missing_prerequisites(
    *, has_llm_key: bool, has_token_enc_key: bool, allows_private_urls: bool, api_key: str
) -> list[str]:
    missing: list[str] = []
    if not has_llm_key:
        missing.append("an LLM key (GEMINI_API_KEY or GROQ_API_KEY)")
    if not has_token_enc_key:
        missing.append("TOKEN_ENC_KEY")
    if not allows_private_urls:
        missing.append("WEBHOOK_ALLOW_PRIVATE_URLS=true")
    if not api_key:
        missing.append(f"{API_KEY_ENV} (an admin key from `make api-key`)")
    return missing


def judge_item(item: dict[str, Any], *, expect_laya_down: bool) -> list[str]:
    """Return a list of problems (empty = pass)."""
    problems: list[str] = []
    if item.get("status") != "awaiting_approval":
        problems.append(f"status is {item.get('status')!r}, expected 'awaiting_approval'")
    if item.get("niche") != "tech_stack":
        problems.append(f"niche is {item.get('niche')!r}, expected 'tech_stack'")
    options = (item.get("decision") or {}).get("options") or []
    if len(options) < MIN_OPTIONS:
        problems.append(f"{len(options)} decision options, expected >= {MIN_OPTIONS}")
    if expect_laya_down:
        shadow = (item.get("triage") or {}).get("shadow") or {}
        if not isinstance(shadow, dict) or shadow.get("error") != "laya_unavailable":
            problems.append("triage.shadow.error is not 'laya_unavailable'")
    return problems


def _poll(client: httpx.Client, item_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + POLL_TIMEOUT_S
    item: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/v1/items/{item_id}")
        response.raise_for_status()
        item = response.json()
        if item.get("status") == "awaiting_approval" or item.get("status") in TERMINAL_BAD:
            return item
        time.sleep(POLL_INTERVAL_S)
    return item


def run_live(base_url: str, api_key: str, args: argparse.Namespace) -> int:
    headers = {"Authorization": f"Bearer {api_key}"}
    with httpx.Client(base_url=base_url, headers=headers, timeout=30) as client:
        client.get("/health").raise_for_status()
        if args.webhook_url:
            sub = client.post(
                "/v1/subscriptions",
                json={
                    "url": args.webhook_url,
                    "events": ["decision.made"],
                    "secret": args.webhook_secret,
                },
            )
            sub.raise_for_status()
            print("L2: subscribed", args.webhook_url)  # noqa: T201 - CLI output
        created = client.post(
            "/v1/items",
            json={
                "source": "manual",
                "source_ref": f"accept-p1-{uuid.uuid4().hex[:12]}",
                "payload": {"text": BRIEF},
            },
        )
        created.raise_for_status()
        item_id = str(created.json()["id"])
        print(f"L1: posted item {item_id}, polling up to {POLL_TIMEOUT_S}s")  # noqa: T201
        item = _poll(client, item_id)
        problems = judge_item(item, expect_laya_down=args.expect_laya_down)
        decision = item.get("decision") or {}
        print(  # noqa: T201
            f"status={item.get('status')} niche={item.get('niche')} "
            f"options={[o.get('id') for o in decision.get('options', [])]} "
            f"recommended={decision.get('recommended')}"
        )
        print("rationale:", decision.get("rationale"))  # noqa: T201
        if problems:
            for problem in problems:
                print("FAIL:", problem)  # noqa: T201
            return 1
        if args.webhook_url:
            approved = client.post(f"/v1/items/{item_id}/decision", json={"verdict": "approve"})
            approved.raise_for_status()
            print("L2: approved; check the receiver for 'signature OK decision.made'")  # noqa: T201
    print("PASS")  # noqa: T201
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live Phase 1 acceptance (L1-L3).")
    parser.add_argument("--base-url", default=None, help="default: APP_BASE_URL setting")
    parser.add_argument("--webhook-url", default=None, help="L2: receiver URL to subscribe")
    parser.add_argument("--webhook-secret", default=DEFAULT_SUBSCRIPTION_SECRET)
    parser.add_argument("--expect-laya-down", action="store_true", help="L3 assertion")
    args = parser.parse_args(argv)

    settings = get_settings()
    api_key = os.environ.get(API_KEY_ENV, "")
    missing = missing_prerequisites(
        has_llm_key=bool(
            settings.gemini_api_key.get_secret_value() or settings.groq_api_key.get_secret_value()
        ),
        has_token_enc_key=bool(settings.token_enc_key.get_secret_value()),
        allows_private_urls=settings.webhook_allow_private_urls,
        api_key=api_key,
    )
    if missing:
        print(f"skipped: missing {', '.join(missing)}")  # noqa: T201 - CLI output
        return 0
    try:
        return run_live(args.base_url or settings.app_base_url, api_key, args)
    except httpx.HTTPError as error:
        print(f"FAIL: API call failed: {type(error).__name__}: {error}")  # noqa: T201
        return 1


if __name__ == "__main__":
    sys.exit(main())
