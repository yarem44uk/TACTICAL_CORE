"""WO-069 — Benchmark metrics: WER / CER / callsign / RTF (pure functions).

Deterministic, stdlib-only and engine-agnostic.  Accuracy metrics are computed
ONLY when an explicit human reference exists; with no reference the caller
records ``reference_available=false`` and the metric stays NOT_MEASURED.  No
model output is ever used as a substitute for a human reference.

One normalization function is used for every engine so that no engine is
advantaged by preprocessing differences.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import math
import re
import statistics
import unicodedata

NOT_MEASURED = "NOT_MEASURED"

# callsign outcome vocabulary
EXACT_MATCH = "EXACT_MATCH"
NORMALIZED_MATCH = "NORMALIZED_MATCH"
MISSED = "MISSED"
FALSE = "FALSE"
NOT_PRESENT = "NOT_PRESENT"

_APOSTROPHES = "\u2019\u02bc\u2018\u2032`'"


def normalize(text: str | None) -> str:
    """WO-069 deterministic transcript normalization (one function, all engines).

    Rules: NFKC unicode; lowercase; apostrophes unified; dashes unified to '-';
    punctuation reduced to spaces; whitespace collapsed.
    """
    if text is None:
        return ""
    out = unicodedata.normalize("NFKC", text)
    out = out.lower()
    for apostrophe in _APOSTROPHES:
        out = out.replace(apostrophe, "'")
    for dash in "\u2010\u2011\u2013\u2014":
        out = out.replace(dash, "-")
    out = re.sub(r"[^\w\s'\u0400-\u04ff-]", " ", out, flags=re.UNICODE)
    return re.sub(r"\s+", " ", out).strip()


def _levenshtein(reference: list, hypothesis: list) -> int:
    if not reference:
        return len(hypothesis)
    if not hypothesis:
        return len(reference)
    previous = list(range(len(hypothesis) + 1))
    for i, ref_item in enumerate(reference, 1):
        current = [i]
        for j, hyp_item in enumerate(hypothesis, 1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (ref_item != hyp_item),
                )
            )
        previous = current
    return previous[-1]


def wer(reference: str | None, hypothesis: str | None) -> float | str:
    """Word error rate = (S+D+I)/N against a human reference.

    Returns NOT_MEASURED when no reference exists (never 0.0, never a guess).
    """
    if reference is None or not str(reference).strip():
        return NOT_MEASURED
    ref = normalize(reference).split()
    hyp = normalize(hypothesis).split()
    if not ref:
        return NOT_MEASURED
    return _levenshtein(ref, hyp) / len(ref)


def cer(reference: str | None, hypothesis: str | None) -> float | str:
    """Character error rate against a human reference (NOT_MEASURED if absent)."""
    if reference is None or not str(reference).strip():
        return NOT_MEASURED
    ref = list(normalize(reference).replace(" ", ""))
    hyp = list(normalize(hypothesis).replace(" ", ""))
    if not ref:
        return NOT_MEASURED
    return _levenshtein(ref, hyp) / len(ref)


def exact_match(reference: str | None, hypothesis: str | None) -> bool | str:
    """Normalized exact match (NOT_MEASURED when no reference exists)."""
    if reference is None or not str(reference).strip():
        return NOT_MEASURED
    return normalize(reference) == normalize(hypothesis)


def _alnum(text: str | None) -> str:
    return re.sub(r"[^0-9a-z\u0400-\u04ff]", "", normalize(text))


def callsign_outcome(reference_callsign: str | None, hypothesis: str | None) -> str:
    """Callsign evaluation, kept SEPARATE from transcript WER/CER.

    The human callsign is matched against the normalized hypothesis:
      EXACT_MATCH       — normalized reference equals the normalized hypothesis
      NORMALIZED_MATCH  — alphanumeric-only reference appears in the hypothesis
      MISSED            — no reference callsign detected in the hypothesis
    """
    if reference_callsign is None or not str(reference_callsign).strip():
        return NOT_MEASURED
    ref = normalize(reference_callsign)
    hyp = normalize(hypothesis)
    if not hyp:
        return MISSED
    if ref == hyp:
        return EXACT_MATCH
    ref_key = _alnum(reference_callsign)
    if ref_key and ref_key in _alnum(hypothesis):
        return NORMALIZED_MATCH
    return MISSED


def real_time_factor(processing_seconds: float | None, audio_seconds: float | None):
    """RTF = processing_time / audio_duration (NOT_MEASURED if not computable)."""
    if processing_seconds is None or audio_seconds is None:
        return NOT_MEASURED
    if audio_seconds <= 0:
        return NOT_MEASURED
    return processing_seconds / audio_seconds


def percentile(values: list[float], pct: float):
    """Nearest-rank percentile (deterministic; no interpolation ambiguity)."""
    if not values:
        return NOT_MEASURED
    ordered = sorted(values)
    rank = max(1, min(len(ordered), math.ceil(pct / 100.0 * len(ordered))))
    return ordered[rank - 1]


def median(values: list[float]):
    return statistics.median(values) if values else NOT_MEASURED
