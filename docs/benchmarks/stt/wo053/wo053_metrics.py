"""WO-053 — Deterministic WER / CER / exact-match metrics.

Every accuracy metric uses :mod:`wo053_normalize` so all candidates share one
normalization.  These are pure functions over (reference, hypothesis) strings;
they never invoke an STT engine.

Definitions:
    WER = (S + D + I) / len(reference_words)
        where S/D/I are substitutions/deletions/insertions from the
        word-level Levenshtein alignment, and len(reference_words) is the
        number of words in the normalized reference.
    CER = char_edit_distance / len(reference_char_stream)
        where char_edit_distance is Levenshtein over the normalized, space-free
        character stream and len(reference_char_stream) is its length.
    exact_match = normalized reference == normalized hypothesis.

A WER/CER of 0.0 means perfect match.  A denominator of 0 (empty reference)
yields 0.0 if the hypothesis is also empty, otherwise 1.0 (documented).

Author: Tactical Core Engineering Team
"""

from __future__ import annotations

from wo053_normalize import (
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
                    prev[j] + 1,       # deletion
                    cur[j - 1] + 1,    # insertion
                    prev[j - 1] + cost,  # substitution / match
                )
            )
        prev = cur
    return prev[-1]


def word_edit_counts(ref_words: list[str], hyp_words: list[str]):
    """Return (substitutions, deletions, insertions) for the word alignment."""
    n, m = len(ref_words), len(hyp_words)
    # DP over alignment, tracking counts via backtrace-free accumulation.
    # We use the standard Levenshtein distance; counts derived from the
    # edit script are deterministic (ties broken by substitution > deletion >
    # insertion order below).
    INF = float("inf")
    # dp[i][j] = distance
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
    # Backtrace to recover counts (deterministic tie-break order).
    i, j = n, m
    subs = deletes = inserts = 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref_words[i - 1] == hyp_words[j - 1] and dp[i][j] == dp[i - 1][j - 1]:
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
        else:
            # Should be unreachable; break defensively.
            break
    return subs, deletes, inserts


def wer(reference: str, hypothesis: str) -> float:
    """Word error rate over normalized reference/hypothesis."""
    ref_words = tokenize_words(normalize_text(reference))
    hyp_words = tokenize_words(normalize_text(hypothesis))
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    subs, deletes, inserts = word_edit_counts(ref_words, hyp_words)
    return (subs + deletes + inserts) / len(ref_words)


def cer(reference: str, hypothesis: str) -> float:
    """Character error rate over the normalized space-free char stream."""
    ref_chars = normalized_char_stream(normalize_text(reference))
    hyp_chars = normalized_char_stream(normalize_text(hypothesis))
    if not ref_chars:
        return 0.0 if not hyp_chars else 1.0
    return levenshtein(ref_chars, hyp_chars) / len(ref_chars)


def exact_match(reference: str, hypothesis: str) -> bool:
    """Whether normalized reference equals normalized hypothesis."""
    return normalize_text(reference) == normalize_text(hypothesis)
