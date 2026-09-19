"""WO-069 — benchmark unit tests: metrics.

Deterministic, no engine, no model, no dataset.

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

import wo069_metrics as M


def test_normalize_is_deterministic_and_unicode_safe():
    assert M.normalize("  Привіт,  СВІТ!  ") == "привіт світ"
    assert M.normalize("Дон\u2019т") == M.normalize("дон'т")
    assert M.normalize(None) == ""


def test_wer_perfect_and_imperfect():
    assert M.wer("а б в", "а б в") == 0.0
    assert M.wer("а б в", "а б г") == pytest.approx(1 / 3)
    assert M.wer("а б в", "а б в г") == pytest.approx(1 / 3)  # one insertion


def test_wer_without_reference_is_not_measured():
    assert M.wer(None, "будь що") == M.NOT_MEASURED
    assert M.wer("   ", "будь що") == M.NOT_MEASURED


def test_cer_bounds():
    assert M.cer("абв", "абв") == 0.0
    assert M.cer("абв", "абг") == pytest.approx(1 / 3)
    assert M.cer(None, "абв") == M.NOT_MEASURED


def test_callsign_outcomes_are_separate_from_wer():
    assert M.callsign_outcome("АЛЬФА", "АЛЬФА") == M.EXACT_MATCH
    assert M.callsign_outcome("АЛЬФА", "це альфа один") == M.NORMALIZED_MATCH
    assert M.callsign_outcome("ALPHA", "ALPHA") == M.EXACT_MATCH
    assert M.callsign_outcome("ALPHA", "alpha one") == M.NORMALIZED_MATCH
    assert M.callsign_outcome("ALPHA", "щось інше") == M.MISSED
    assert M.callsign_outcome("ALPHA", "") == M.MISSED
    assert M.callsign_outcome(None, "будь що") == M.NOT_MEASURED


def test_real_time_factor():
    assert M.real_time_factor(2.0, 4.0) == 0.5
    assert M.real_time_factor(1.0, 0.0) == M.NOT_MEASURED
    assert M.real_time_factor(None, 1.0) == M.NOT_MEASURED


def test_percentile_nearest_rank():
    values = [1.0, 2.0, 3.0, 4.0]
    assert M.percentile(values, 50) == 2.0
    assert M.percentile(values, 95) == 4.0
    assert M.percentile([], 95) == M.NOT_MEASURED


def test_median_empty():
    assert M.median([]) == M.NOT_MEASURED
