"""WO-067 — Deterministic WER / CER / callsign metrics (benchmark-only).

Pure functions over (reference, hypothesis).  They never invoke an STT engine
and never invent a reference.

Definitions:
    WER = (S + D + I) / len(reference_words)
        S/D/I from the word-level Levenshtein alignment; the denominator is the
        number of words in the normalized reference.
    CER = char_edit_distance / len(reference_char_stream)
        Levenshtein over the normalized, space-free character stream.
    exact_match = normalized reference == normalized hypothesis.

Denominator 0 (empty reference): 0.0 when the hypothesis is also empty,
otherwise 1.0 (documented, deterministic).

Callsign metric (WO-067 §13): computed ONLY when the human ground truth
explicitly carries a callsign.  Never invented.  Outcomes are distinguished:
    EXACT_MATCH / NORMALIZED_MATCH / MISSED / FALSE / NOT_PRESENT / NOT_MEASURED

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

from wo067_normalize import (
    normalize_text,
    normalized_char_stream,
    tokenize_words,
)


def levenshtein(a: str, b: str) -> int:
    """Classic Levenshtein edit distance (iterative DP)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(
                min(
                    prev[j] + 1,
                    cur[j - 1] + 1,
                    prev[j - 1] + cost,
                )
            )
        prev = cur
    return prev[-1]


def word_edit_counts(ref_words: list[str], hyp_words: list[str]) -> tuple[int, int, int]:
    """Return (substitutions, deletions, insertions) for the word alignment."""
    n, m = len(ref_words), len(hyp_words)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref_words[i - 1] == hyp_words[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )
    i, j = n, m
    subs = deletes = inserts = 0
    while i > 0 or j > 0:
        if (
            i > 0
            and j > 0
            and ref_words[i - 1] == hyp_words[j - 1]
            and dp[i][j] == dp[i - 1][j - 1]
        ):
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            subs += 1
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            deletes += 1
            i -= 1
        elif j > 0 and dp[i][j] == dp[i][j - 1] + 1:
            inserts += 1
            j -= 1
        else:  # pragma: no cover - defensive
            break
    return subs, deletes, inserts


def wer(reference: str | None, hypothesis: str | None) -> float:
    """Word error rate over normalized reference/hypothesis."""
    ref_words = tokenize_words(normalize_text(reference))
    hyp_words = tokenize_words(normalize_text(hypothesis))
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    subs, deletes, inserts = word_edit_counts(ref_words, hyp_words)
    return (subs + deletes + inserts) / len(ref_words)


def cer(reference: str | None, hypothesis: str | None) -> float:
    """Character error rate over the normalized space-free char stream."""
    ref_chars = normalized_char_stream(normalize_text(reference))
    hyp_chars = normalized_char_stream(normalize_text(hypothesis))
    if not ref_chars:
        return 0.0 if not hyp_chars else 1.0
    return levenshtein(ref_chars, hyp_chars) / len(ref_chars)


def exact_match(reference: str | None, hypothesis: str | None) -> bool:
    """Whether normalized reference equals normalized hypothesis."""
    return normalize_text(reference) == normalize_text(hypothesis)


# ---------------------------------------------------------------------------
# RTF — explicit definition required by WO-067 §10
# ---------------------------------------------------------------------------

def real_time_factor(
    processing_seconds: float,
    audio_duration_seconds: float | None,
) -> float | None:
    """RTF = processing_time / audio_duration.

    RTF < 1.0 means faster than real time.  Returns ``None`` when the audio
    duration is not a usable positive number: RTF is then NOT MEASURED rather
    than invented.
    """
    if audio_duration_seconds is None or audio_duration_seconds <= 0:
        return None
    return processing_seconds / audio_duration_seconds


# ---------------------------------------------------------------------------
# Callsign metric — only when human ground truth explicitly provides one
# ---------------------------------------------------------------------------

EXACT_MATCH = "EXACT_MATCH"
NORMALIZED_MATCH = "NORMALIZED_MATCH"
MISSED = "MISSED"
FALSE = "FALSE"
NOT_PRESENT = "NOT_PRESENT"
NOT_MEASURED = "NOT_MEASURED"


def _alnum_stream(text: str | None) -> str:
    """Alphanumeric-only lowercase stream used for documented normalization."""
    norm = normalize_text(text)
    return "".join(ch for ch in norm if ch.isalnum())


def callsign_outcome(
    reference_callsign: str | None,
    hypothesis_text: str | None,
) -> str:
    """Classify a callsign against a hypothesis transcript.

    ``reference_callsign`` must come from explicit human ground truth.  When it
    is absent the result is NOT_MEASURED (this function is then not called by
    the metric aggregator at all — kept here so the policy is explicitly
    testable).
    """
    if not reference_callsign or not str(reference_callsign).strip():
        return NOT_MEASURED
    ref = normalize_text(reference_callsign)
    hyp_norm = normalize_text(hypothesis_text)
    if not ref:
        return NOT_MEASURED
    hyp_tokens = hyp_norm.split()
    if ref in hyp_tokens:
        return EXACT_MATCH
    ref_alnum = _alnum_stream(reference_callsign)
    if ref_alnum and ref_alnum in _alnum_stream(hypothesis_text):
        return NORMALIZED_MATCH
    return MISSED