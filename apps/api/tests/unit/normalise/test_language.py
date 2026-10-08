"""Language detection heuristics (FR-13)."""

import pytest

from app.normalise.language import detect_language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ਸਾਡੇ ਸਕੂਲ ਲਈ ਫੀਸ ਦਾ ਹਿਸਾਬ ਚਾਹੀਦਾ ਹੈ", "pa"),
        ("हमारे स्कूल के लिए फीस का हिसाब चाहिए", "hi"),
        ("mera school ka fee system kaise chalega, aap batao kya karna hai", "hinglish"),
        ("We need a fee system for twelve schools in Punjab.", "en"),
        ("", "en"),
        ("Invoice 2024-11 attached. Please review the Hindi translation: नमस्ते", "en"),
    ],
)
def test_detect_language(text: str, expected: str) -> None:
    assert detect_language(text) == expected


def test_one_hindi_function_word_is_still_english() -> None:
    assert detect_language("Please send the hai report today") == "en"
