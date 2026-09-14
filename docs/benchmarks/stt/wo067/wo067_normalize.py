"""WO-067 — Deterministic transcript normalization (benchmark-only).

One normalization for every candidate and every engine.  WER/CER are never
computed under a per-candidate or per-engine normalization policy.

Policy is deliberately identical to the WO-053 STT benchmark layer so that
results remain comparable across benchmark generations:
    * Unicode NFKC normalisation first.
    * casefold (lowercase).
    * Keep letters (incl. Ukrainian), digits and the apostrophe (U+0027/U+2019).
    * Every other punctuation/symbol becomes a space.
    * Whitespace collapsed to single spaces and trimmed.
    * Word tokens = split on whitespace.

This module is standalone (stdlib only).  It imports nothing from the production
seam and nothing from the WO-053 layer, so the WO-067 benchmark layer can be
removed without touching any other package.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import unicodedata

_APOSTROPHES = frozenset({"\u0027", "\u2019"})


def _is_kept_char(ch: str) -> bool:
    """Whether ``ch`` survives tokenization as part of a word."""
    cat = unicodedata.category(ch)
    if cat.startswith(("L", "N", "M")):
        return True
    return ch in _APOSTROPHES


def normalize_text(text: str | None) -> str:
    """Normalize a transcript into a canonical, whitespace-collapsed string."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.casefold()
    out: list[str] = []
    for ch in text:
        out.append(ch if _is_kept_char(ch) else " ")
    return " ".join("".join(out).split())


def tokenize_words(normalized: str) -> list[str]:
    """Split a normalized string into word tokens (whitespace-delimited)."""
    return normalized.split()


def normalized_char_stream(normalized: str) -> str:
    """Return the compact character stream for CER (word boundaries removed)."""
    return "".join(normalized.split())


def words(text: str | None) -> list[str]:
    """Convenience: normalize then tokenize into words."""
    return tokenize_words(normalize_text(text))