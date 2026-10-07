"""Untrusted text handling: every remote string reaching a prompt passes as_data (NFR-05, FR-42)."""

import re

MAX_DATA_CHARS = 8000
TRUNCATION_MARKER = "…[truncated]"

# Keep \n and \t; drop \r, DEL and the other C0/C1 control characters.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
# Any open or close tag of the llm.fence() wrapper, tolerant of whitespace and case.
_FENCE_TAG = re.compile(r"<(\s*/?\s*item_content)", re.IGNORECASE)


def as_data(text: str, *, max_chars: int = MAX_DATA_CHARS) -> str:
    """Clean, cap and neutralize fence tags. Does not wrap (llm.fence does)."""
    if not isinstance(text, str):
        raise TypeError(f"as_data expects str, got {type(text).__name__}")
    cleaned = _CONTROL_CHARS.sub("", text)
    cleaned = _FENCE_TAG.sub(r"‹\1", cleaned)
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + TRUNCATION_MARKER
    return cleaned
