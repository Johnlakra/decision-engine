"""Opportunity Radar -> Decision Engine bridge (FR-96, docs/CONNECTORS.md).

Posts the radar's scored news items to ``POST /v1/items`` as ``source=radar`` with
``hints.niche=news_radar``. The Decision Engine side does the Laya triage and the approval queue.
Standalone on purpose: the radar does not import the decision-engine package.

Usage (from the radar repo, after exporting its items as JSON):
    DE_API_URL=https://de.example.com DE_API_KEY=de_xxx \\
        python radar_bridge.py radar_items.json

``radar_items.json`` is a list of objects with the radar's ``Item`` fields: topic, url, title,
summary, source, score, category, action, urgency, why, personal, fetched_at (ISO 8601).
Re-running is safe: ``source_ref`` is the item URL, so repeats return the stored item.
"""

import hashlib
import json
import os
import sys
from collections.abc import Iterable, Mapping
from typing import Any

import httpx

SOURCE = "radar"
NICHE = "news_radar"
MAX_REF_CHARS = 300  # IngestItemIn.source_ref max_length
MAX_URL_CHARS = 2000
MAX_TITLE_CHARS = 500
MAX_BODY_CHARS = 4000
PAYLOAD_FIELDS = ("topic", "source", "score", "category", "action", "urgency", "why", "personal")
INGEST_PATH = "/v1/items"
TIMEOUT_S = 15.0


def _text(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _source_ref(url: str) -> str:
    if len(url) <= MAX_REF_CHARS:
        return url
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def map_radar_item(item: Mapping[str, Any]) -> dict[str, Any] | None:
    """One radar item -> one ``/v1/items`` body. None when the item has no usable https URL."""
    url = _text(item.get("url"), MAX_URL_CHARS)
    if not url.startswith("https://"):
        return None
    payload = {field: item[field] for field in PAYLOAD_FIELDS if item.get(field) is not None}
    payload["fetched_at"] = item.get("fetched_at")
    return {
        "source": SOURCE,
        "source_ref": _source_ref(url),
        "payload": payload,
        "hints": {
            "niche": NICHE,
            "title": _text(item.get("title"), MAX_TITLE_CHARS) or url,
            "body": _text(item.get("summary"), MAX_BODY_CHARS) or None,
            "url": url,
        },
    }


def map_all(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    mapped = [map_radar_item(item) for item in items]
    return [body for body in mapped if body is not None]


def post_items(
    bodies: list[dict[str, Any]], base_url: str, api_key: str, client: httpx.Client
) -> tuple[int, int]:
    """POST each body. Returns ``(accepted, failed)``; a failure is reported, never fatal."""
    accepted = 0
    failed = 0
    headers = {"Authorization": f"Bearer {api_key}"}
    for body in bodies:
        response = client.post(f"{base_url.rstrip('/')}{INGEST_PATH}", json=body, headers=headers)
        if response.status_code in (200, 201):
            accepted += 1
        else:
            failed += 1
            print(f"failed {response.status_code}: {body['source_ref'][:40]}", file=sys.stderr)
    return accepted, failed


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: radar_bridge.py radar_items.json", file=sys.stderr)
        return 2
    base_url = os.environ.get("DE_API_URL", "")
    api_key = os.environ.get("DE_API_KEY", "")
    if not base_url or not api_key:
        print("set DE_API_URL and DE_API_KEY", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as handle:
        items = json.load(handle)
    bodies = map_all(items)
    with httpx.Client(timeout=TIMEOUT_S, trust_env=False) as client:
        accepted, failed = post_items(bodies, base_url, api_key, client)
    print(f"radar items: {accepted} accepted, {failed} failed, {len(items) - len(bodies)} skipped")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
