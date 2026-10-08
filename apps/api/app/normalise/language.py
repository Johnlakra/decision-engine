"""Fast language detection by script and function words, no model (FR-13)."""

import re

GURMUKHI = re.compile(r"[਀-੿]")
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LETTER = re.compile(r"[^\W\d_]")
_WORD = re.compile(r"[a-z]+")

NON_LATIN_SHARE = 0.3  # of all letters, to call the text Gurmukhi or Devanagari
MIN_HINDI_WORDS = 2
# Romanised Hindi/Punjabi function words that are rare in English.
HINDI_WORDS = frozenset(
    "hai hain nahi nahin kya mera meri mere aap hum tum kaise kab bhi aur toh tha thi raha rahi "
    "chahiye hoga kyun kyu mein ko ka ki ke karna karo batao".split()
)


def detect_language(text: str) -> str:
    """Gurmukhi -> pa, Devanagari -> hi, Latin with >= 2 Hindi words -> hinglish, else en."""
    letters = len(_LETTER.findall(text))
    if letters:
        gurmukhi = len(GURMUKHI.findall(text))
        devanagari = len(DEVANAGARI.findall(text))
        top = max(gurmukhi, devanagari)
        if top / letters >= NON_LATIN_SHARE:
            return "pa" if gurmukhi >= devanagari else "hi"
    hits = {word for word in _WORD.findall(text.lower()) if word in HINDI_WORDS}
    return "hinglish" if len(hits) >= MIN_HINDI_WORDS else "en"
