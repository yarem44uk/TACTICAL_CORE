"""WO-070B deterministic transcript normalization (benchmark-local, no production deps).

One procedure is applied identically to the human reference and to every engine
hypothesis. It never semantically corrects text; it only removes formatting
variance so that WER/CER measure recognition, not typography.

Procedure (exact order):
  1. None / non-str -> "" (empty string).
  2. Unicode normalization: NFC (uniscribe composed form).
  3. Case handling: str.casefold() (locale-independent).
  4. Ukrainian/typographic apostrophes: every variant (U+2019, U+2018, U+02BC,
     U+0060, U+00B4, U+02B9, U+2032) is mapped to ASCII U+0027 "'".
  5. Punctuation / symbols: any character that is not a letter, a digit, an
     ASCII apostrophe or whitespace is replaced by a single space. This covers
     "." "," "…" "-" "_" "?" "!" quotes etc. Ellipses ("..", "...", "…")
     therefore collapse to whitespace, not to a token.
  6. Tokenization: split on whitespace; leading/trailing apostrophes are
     stripped from each token; empty tokens are dropped.
  7. Whitespace normalization: tokens rejoined with exactly one ASCII space.
  8. Digits are preserved as digits (no number-to-word expansion) so that the
     metric is script-agnostic.
  9. Empty-string handling: a normalization result of "" is a valid, meaningful
     output (empty hypothesis or missing reference), not an error.

The same function is used for reference and hypotheses; there is no branch that
favours either side.
"""

import unicodedata

_APOSTROPHE_VARIANTS = (
    "\u2019",  # RIGHT SINGLE QUOTATION MARK
    "\u2018",  # LEFT SINGLE QUOTATION MARK
    "\u02bc",  # MODIFIER LETTER APOSTROPHE
    "\u0060",  # GRAVE ACCENT
    "\u00b4",  # ACUTE ACCENT
    "\u02b9",  # MODIFIER LETTER PRIME
    "\u2032",  # PRIME
)
_ASCII_APOSTROPHE = "'"

NORMALIZATION_ID = "wo070b-normalize-v1"


def normalize_text(text):
    """Return the deterministic normalized form of *text*.

    Step order is fixed and documented above; identical for reference and
    hypothesis. Returns "" for None or for text that normalizes to nothing.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # 2. Unicode normalization
    s = unicodedata.normalize("NFC", text)

    # 3. Case handling
    s = s.casefold()

    # 4. Apostrophe unification
    for variant in _APOSTROPHE_VARIANTS:
        s = s.replace(variant, _ASCII_APOSTROPHE)

    # 5. Punctuation / symbol removal
    chars = []
    for ch in s:
        if ch.isalnum() or ch == _ASCII_APOSTROPHE or ch.isspace():
            chars.append(ch)
        else:
            chars.append(" ")
    s = "".join(chars)

    # 6-7. Tokenization + whitespace normalization
    tokens = [tok.strip(_ASCII_APOSTROPHE) for tok in s.split()]
    tokens = [tok for tok in tokens if tok]
    return " ".join(tokens)


def normalize_tokens(text):
    """Normalized whitespace-separated word tokens (WER unit)."""
    normalized = normalize_text(text)
    return normalized.split(" ") if normalized else []


def normalize_characters(text):
    """Normalized character sequence with whitespace removed (CER unit)."""
    return normalize_text(text).replace(" ", "")
