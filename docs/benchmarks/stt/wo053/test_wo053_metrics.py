"""WO-053 — Tests for transcript normalization and WER/CER/exact-match metrics.

These tests validate the METRICS MECHANICS only.  They do NOT assert any STT
accuracy, do not invoke an engine, and are not evidence of real STT quality.

Author: Tactical Core Engineering Team
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from wo053_normalize import (  # noqa: E402
    normalize_text,
    normalized_char_stream,
    tokenize_words,
    words,
)
from wo053_metrics import (  # noqa: E402
    cer,
    exact_match,
    levenshtein,
    wer,
)


def test_levenshtein_known():
    assert levenshtein("", "") == 0
    assert levenshtein("a", "") == 1
    assert levenshtein("", "ab") == 2
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein("abc", "abc") == 0


def test_normalize_lowercase_and_casefold():
    assert normalize_text("Hello WORLD") == "hello world"


def test_normalize_removes_punctuation():
    assert normalize_text("Hi, there! How are you?") == "hi there how are you"


def test_normalize_collapses_whitespace():
    assert normalize_text("  a    b   c  ") == "a b c"


def test_normalize_keeps_apostrophe():
    assert normalize_text("м'ята") == "м'ята"


def test_normalize_hyphen_becomes_space():
    # Hyphen is a word separator by policy.
    assert normalize_text("two-way") == "two way"


def test_normalize_keeps_digits():
    assert normalize_text("alpha 21") == "alpha 21"


def test_normalize_keeps_ukrainian_letters():
    assert normalize_text("Повітряна тривога") == "повітряна тривога"


def test_normalize_strips_special_chars():
    assert normalize_text("ALPHA@21#") == "alpha 21"


def test_tokenize_words():
    assert tokenize_words(normalize_text("one two three")) == ["one", "two", "three"]


def test_normalized_char_stream_removes_spaces():
    assert normalized_char_stream(normalize_text("a b c")) == "abc"


def test_words_convenience():
    assert words("Повітряна тривога") == ["повітряна", "тривога"]


def test_wer_perfect_match_zero():
    assert wer("alpha two one", "alpha two one") == 0.0


def test_wer_substitution():
    # one word substituted out of three
    assert abs(wer("alpha two one", "alpha two two") - 1.0 / 3.0) < 1e-9


def test_wer_insertion():
    # one inserted word
    assert abs(wer("alpha two", "alpha two one") - 1.0 / 2.0) < 1e-9


def test_wer_deletion():
    assert abs(wer("alpha two one", "alpha two") - 1.0 / 3.0) < 1e-9


def test_wer_empty_reference():
    assert wer("", "") == 0.0
    assert wer("", "something") == 1.0


def test_cer_perfect_match_zero():
    assert cer("alpha", "alpha") == 0.0


def test_cer_substitution():
    assert abs(cer("abc", "abd") - 1.0 / 3.0) < 1e-9


def test_cer_insertion():
    assert abs(cer("abc", "abcd") - 1.0 / 3.0) < 1e-9


def test_cer_ignores_word_boundaries():
    # "ab cd" vs "abcd" have the same char stream -> 0 CER
    assert cer("ab cd", "abcd") == 0.0


def test_cer_empty_reference():
    assert cer("", "") == 0.0
    assert cer("", "x") == 1.0


def test_exact_match():
    assert exact_match("Alpha 21", "alpha 21") is True
    assert exact_match("Alpha 21", "alpha 22") is False


def test_wer_uses_same_normalization_as_exact_match():
    # Punctuation-only difference is not an error.
    assert wer("Alpha 21!", "alpha 21") == 0.0
