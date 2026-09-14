"""WO-067 — benchmark unit tests: normalization, WER/CER, RTF, callsigns.

Pure-function mechanics only.  No engine, no model, no network.
Any audio referenced here is SYNTHETIC TEST FIXTURE and never benchmark evidence.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import wo067_metrics as M
from wo067_normalize import (
    normalize_text,
    normalized_char_stream,
    tokenize_words,
    words,
)

# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def test_normalize_casefold_and_punctuation() -> None:
    assert normalize_text("Привіт, СВІТЕ!") == "привіт світе"


def test_normalize_keeps_apostrophe_and_digits() -> None:
    assert normalize_text("п'ять 5") == "п'ять 5"
    assert normalize_text("п\u2019ять") == "п\u2019ять"


def test_normalize_collapses_whitespace() -> None:
    assert normalize_text("  a \t b\n\nc  ") == "a b c"


def test_normalize_empty() -> None:
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


def test_tokenize_and_char_stream() -> None:
    norm = normalize_text("Привіт світе")
    assert tokenize_words(norm) == ["привіт", "світе"]
    assert normalized_char_stream(norm) == "привітсвіте"


def test_words_convenience() -> None:
    assert words("Аб, вг!") == ["аб", "вг"]


# ---------------------------------------------------------------------------
# Levenshtein / WER / CER
# ---------------------------------------------------------------------------

def test_levenshtein_basic() -> None:
    assert M.levenshtein("", "") == 0
    assert M.levenshtein("abc", "abc") == 0
    assert M.levenshtein("abc", "") == 3
    assert M.levenshtein("", "abc") == 3
    assert M.levenshtein("kitten", "sitting") == 3


def test_word_edit_counts_sub_del_ins() -> None:
    subs, dels, ins = M.word_edit_counts(["a", "b", "c"], ["a", "x", "c"])
    assert (subs, dels, ins) == (1, 0, 0)
    subs, dels, ins = M.word_edit_counts(["a", "b"], ["a"])
    assert (subs, dels, ins) == (0, 1, 0)
    subs, dels, ins = M.word_edit_counts(["a"], ["a", "b"])
    assert (subs, dels, ins) == (0, 0, 1)


def test_wer_perfect_and_partial() -> None:
    assert M.wer("привіт світ", "привіт світ") == 0.0
    # one substitution over four reference words
    assert M.wer("а б в г", "а б в д") == pytest.approx(0.25)


def test_wer_empty_reference_semantics() -> None:
    assert M.wer("", "") == 0.0
    assert M.wer("", "щось") == 1.0


def test_cer_perfect_and_partial() -> None:
    assert M.cer("привіт", "привіт") == 0.0
    # one substitution over 4 chars
    assert M.cer("abcd", "abce") == pytest.approx(0.25)


def test_cer_empty_reference_semantics() -> None:
    assert M.cer("", "") == 0.0
    assert M.cer("", "x") == 1.0


def test_cer_is_case_and_punctuation_insensitive() -> None:
    assert M.cer("Привіт, світ!", "привіт світ") == 0.0


def test_exact_match() -> None:
    assert M.exact_match("Привіт, світ", "привіт світ") is True
    assert M.exact_match("привіт", "бувай") is False


# ---------------------------------------------------------------------------
# RTF — definition must be explicit and never invented
# ---------------------------------------------------------------------------

def test_rtf_definition() -> None:
    # RTF = processing_time / audio_duration
    assert M.real_time_factor(2.0, 4.0) == 0.5
    assert M.real_time_factor(1.0, 1.0) == 1.0


def test_rtf_not_measured_when_duration_invalid() -> None:
    assert M.real_time_factor(1.0, 0.0) is None
    assert M.real_time_factor(1.0, -1.0) is None
    assert M.real_time_factor(1.0, None) is None


# ---------------------------------------------------------------------------
# Callsign metric — only from explicit human ground truth
# ---------------------------------------------------------------------------

def test_callsign_not_measured_without_reference() -> None:
    assert M.callsign_outcome(None, "будь-який текст") == M.NOT_MEASURED
    assert M.callsign_outcome("", "текст") == M.NOT_MEASURED
    assert M.callsign_outcome("   ", "текст") == M.NOT_MEASURED


def test_callsign_exact_match() -> None:
    assert M.callsign_outcome("Сокіл", "привіт сокіл як чуєш") == M.EXACT_MATCH


def test_callsign_normalized_match() -> None:
    # alphanumeric-normalized substring (hyphen/punctuation tolerant)
    assert M.callsign_outcome("Сокіл-1", "два сокіл1 на зв'язку") == M.NORMALIZED_MATCH


def test_callsign_missed() -> None:
    assert M.callsign_outcome("Сокіл", "зовсім інший текст") == M.MISSED