"""Structured output helpers: schema prompt, response_format, parse + validate, repair (FR-12)."""

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from app.llm.config import ProviderConfig
from app.llm.errors import StructuredOutputError

_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
MAX_ERROR_CHARS = 1500


def schema_name(schema: type[BaseModel]) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", schema.__name__)[:64]


def schema_instruction(schema: type[BaseModel]) -> str:
    return (
        "Reply with a single JSON object and nothing else (no markdown, no commentary) "
        "that validates against this JSON Schema:\n"
        + json.dumps(schema.model_json_schema(), separators=(",", ":"))
    )


def prepare_messages(
    messages: list[dict[str, Any]], schema: type[BaseModel]
) -> list[dict[str, Any]]:
    """New message list with the schema instruction appended to the system prompt."""
    instruction = schema_instruction(schema)
    result = [dict(m) for m in messages]
    for message in result:
        if message.get("role") == "system":
            message["content"] = f"{message.get('content', '')}\n\n{instruction}"
            return result
    return [{"role": "system", "content": instruction}, *result]


def response_format_for(provider: ProviderConfig, schema: type[BaseModel]) -> dict[str, Any] | None:
    """Native providers get json_schema mode; the rest rely on the schema in the prompt."""
    if provider.json_mode != "native":
        return None
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name(schema),
            "schema": schema.model_json_schema(),
            "strict": False,
        },
    }


def _strip(text: str) -> str:
    cleaned = _THINK_RE.sub("", text).strip()
    match = _FENCE_RE.match(cleaned)
    return match.group(1) if match else cleaned


def parse_and_validate[M: BaseModel](text: str, schema: type[M]) -> M:
    """Parse model output into `schema`; raise StructuredOutputError with a short reason."""
    try:
        return schema.model_validate_json(_strip(text))
    except ValidationError as exc:
        errors = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or '<root>'}: {e['msg']}" for e in exc.errors()
        )
        raise StructuredOutputError(errors[:MAX_ERROR_CHARS], text) from exc


def repair_messages(
    prepared: list[dict[str, Any]], bad_text: str, errors: str
) -> list[dict[str, Any]]:
    """Original conversation plus the faulty reply and what was wrong with it."""
    return [
        *prepared,
        {"role": "assistant", "content": bad_text},
        {
            "role": "user",
            "content": (
                f"That reply was not valid. Problems: {errors}\n"
                "Reply again with only the corrected JSON object."
            ),
        },
    ]
