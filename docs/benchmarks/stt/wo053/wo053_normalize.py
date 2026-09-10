"""WO-053 — Deterministic transcript normalization.

This module defines the ONE normalization used for every candidate in the
WO-053 benchmark.  WER and CER MUST be computed over the same normalization for
every engine; the normalization is never changed per candidate.

Policy (documented in WO-053-STT-BENCHMARK-REPORT.md):
    * Unicode NFKC normalisation first.
    * casefold (lowercase).
    * Keep letters (incl. Ukrainian, Unicode category L), digits (N) and the
      apostrophe (U+0027 and U+2019).
    * Hyphens and every other punctuation/symbol are replaced by a space.
    * Whitespace is collapsed to single spaces and trimmed.
    * Word tokens = split on whitespace.

Author: Tactical Core Engineering Team
"""

from __future__ import annotations

import unicodedata

# Characters that are kept as-is inside a token: letters, digits, apostrophe.
_APOSTROPHES = frozenset({"\u0027", "\u2019"})


def _is_kept_char(ch: str) -> bool:
    """Whether ``ch`` survives tokenization as part of a word."""
    cat = unicodedata.category(ch)
    # L* letters, N* digits, M* marks (combining), P* apostrophe handled below.
    if cat.startswith(("L", "N", "M")):
        return True
    if ch in _APOSTROPHES:
        return True
    return False


def normalize_text(text: str) -> str:
    """Normalize a transcript into a canonical, whitespace-collapsed string.

    Steps: NFKC, casefold, replace every non-kept character with a space,
    collapse runs of spaces, trim.

    Args:
        text: The raw transcript (reference or hypothesis).

    Returns:
        The normalized, lowercase, punctuation-stripped string.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.casefold()
    out: list[str] = []
    for ch in text:
        if _is_kept_char(ch):
            out.append(ch)
        else:
            out.append(" ")
    collapsed = " ".join("".join(out).split())
    return collapsed


def tokenize_words(normalized: str) -> list[str]:
    """Split a normalized string into word tokens (whitespace-delimited)."""
    return normalized.split()


def normalized_char_stream(normalized: str) -> str:
    """Return the compact character stream for CER (spaces removed).

    CER compares the letter/digit/apostrophe stream, not word boundaries.
    """
    return "".join(normalized.split())


def words(text: str) -> list[str]:
    """Convenience: normalize then tokenize into words."""
    return tokenize_words(normalize_text(text))
