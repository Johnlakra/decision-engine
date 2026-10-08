"""Item text for prompts. Everything returned here is untrusted and must be fenced by the caller."""

from typing import Any

from app.llm.fence import fence


def content_text(content: dict[str, Any]) -> str:
    parts = [
        str(content.get("title") or ""),
        f"From: {content['sender']}" if content.get("sender") else "",
        str(content.get("body") or ""),
    ]
    return "\n".join(part for part in parts if part)


def fenced_content(content: dict[str, Any], source: str) -> str:
    return fence(content_text(content), source)
