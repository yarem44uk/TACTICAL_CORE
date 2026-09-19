"""WO-069-CORRECTIVE — benchmark unit tests: WER/CER measurement evidence.

Deterministic; uses synthetic fixtures only (no engine, no model, no real
dataset).  The single real-artifact test proves the WO-068 human-review source
is treated READ-ONLY (its hash still matches the recorded benchmark hash) and is
skipped if the artifact is not staged in this environment.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import csv
import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import wo069_metrics as M
import wo069_wer_evidence as W
from wo069_dataset import DatasetRecord

HUMAN_REVIEW_CSV = "/opt/data/uploads/1789807255-6bf70d4b/human_review.csv"
RECORDED_HUMAN_REVIEW_SHA256 = (
    "21c470b613f1df215b2e71bd154e4237a19462293d68af43aa29a362320af1e5"
)


def _record(message_id: str, reference: str | None = None) -> DatasetRecord:
    record = DatasetRecord(
        message_id=message_id,
        stream_id="S1",
        wav_path=f"/fixture/{message_id}.wav",
        duration_seconds=1.0,
        dataset_sha256="0" * 64,
        human_review_status="REVIEWED",
    )
    record.human_reference_transcript = reference
    record.reference_available = reference is not None
    return record


def _results(engine_texts: dict[str, dict[str, str]]) -> dict:
    engines = []
    for engine in sorted(engine_texts):
        engines.append(
            {
                "engine": engine,
                "engine_status": "COMPLETED",
                "configuration": {"model_path": f"/fixture/{engine}"},
                "records": [
                    {
                        "message_id": message_id,
                        "wav_path": f"/fixture/{message_id}.wav",
                        "audio_duration_seconds": 1.0,
                        "status": "SUCCESS",
                        "text": text,
                        "error": None,
                    }
                    for message_id, text in sorted(engine_texts[engine].items())
                ],
            }
        )
    return {"engines": engines, "dataset": {"record_count": 1}}


# --- 1. reference transcript loading -------------------------------------------------

def test_reference_transcript_loading():
    records = {"msg_0001": _record("msg_0001", "привіт світ")}
    results = _results({"faster_whisper": {"msg_0001": "привіт світ"}})
    rows = W.evaluate(results, records)["rows"]
    row = rows[0]
    assert row["reference"] == "привіт світ"
    assert row["reference_available"] is True
    assert row["reference_token_count"] == 2


# --- 2. hypothesis loading -----------------------------------------------------------

def test_hypothesis_loading_is_raw_and_unmodified():
    records = {"msg_0001": _record("msg_0001", "привіт світ")}
    results = _results({"faster_whisper": {"msg_0001": "  Привіт, СВІТ!  "}})
    row = W.evaluate(results, records)["rows"][0]
    assert row["hypothesis"] == "  Привіт, СВІТ!  "  # raw, whitespace preserved
    assert row["hypothesis_available"] is True


# --- 3. missing reference handling ---------------------------------------------------

def test_missing_reference_is_excluded_and_not_measured():
    records = {"msg_0001": _record("msg_0001", None)}
    results = _results({"faster_whisper": {"msg_0001": "будь-який текст"}})
    data = W.evaluate(results, records)
    row = data["rows"][0]
    assert row["status"] == W.EXCLUDED_NO_HUMAN_REFERENCE
    assert row["exclusion_reason"] == W.EXCLUDED_NO_HUMAN_REFERENCE
    assert row["wer"] == M.NOT_MEASURED
    assert row["cer"] == M.NOT_MEASURED
    assert row["reference"] == W.UNAVAILABLE
    summary = data["summary"][0]
    assert summary["evaluated_records"] == 0
    assert summary["wer"] == M.NOT_MEASURED
    assert summary["wer_status"] == W.NOT_MEASURABLE
    assert summary["excluded_no_reference"] == 1


# --- 4. missing hypothesis handling --------------------------------------------------

def test_missing_hypothesis_is_excluded_and_not_measured():
    records = {"msg_0001": _record("msg_0001", "привіт світ")}
    results = _results({"faster_whisper": {"msg_0001": ""}})
    data = W.evaluate(results, records)
    row = data["rows"][0]
    assert row["status"] == W.EXCLUDED_NO_HYPOTHESIS
    assert row["wer"] == M.NOT_MEASURED
    assert row["cer"] == M.NOT_MEASURED
    assert data["summary"][0]["excluded_no_hypothesis"] == 1


def test_missing_reference_takes_precedence_over_missing_hypothesis():
    """No reference AND no hypothesis: the reference gap is the reported reason."""
    records = {"msg_0001": _record("msg_0001", None)}
    results = _results({"faster_whisper": {"msg_0001": ""}})
    row = W.evaluate(results, records)["rows"][0]
    assert row["status"] == W.EXCLUDED_NO_HUMAN_REFERENCE


# --- 5. deterministic normalization --------------------------------------------------

def test_normalization_policy_is_deterministic_and_documented():
    assert W.normalization_policy() == W.normalization_policy()
    policy = W.normalization_policy()
    assert policy["policy_id"] == W.NORMALIZATION_POLICY_ID
    assert policy["applies_to"] == ["human_reference_transcript", "engine_hypothesis"]
    assert policy["identical_for_all_engines"] is True
    assert json.dumps(policy, sort_keys=True) == json.dumps(
        W.normalization_policy(), sort_keys=True
    )


def test_normalization_ignores_case_and_punctuation_only():
    records = {"msg_0001": _record("msg_0001", "Привіт, світ!")}
    results = _results({"faster_whisper": {"msg_0001": "привіт світ"}})
    row = W.evaluate(results, records)["rows"][0]
    assert row["wer"] == 0.0
    assert row["cer"] == 0.0


# --- 6/7. WER and CER calculation ----------------------------------------------------

def test_wer_cer_calculated_when_reference_and_hypothesis_exist():
    records = {"msg_0001": _record("msg_0001", "а б в")}
    results = _results({"faster_whisper": {"msg_0001": "а б г"}})
    data = W.evaluate(results, records)
    row = data["rows"][0]
    assert row["status"] == W.EVALUATED
    assert row["wer"] == pytest.approx(1 / 3)
    assert row["cer"] == pytest.approx(1 / 3)
    assert row["reference_token_count"] == 3
    assert row["hypothesis_token_count"] == 3
    assert row["exclusion_reason"] == ""


# --- 8. aggregate calculation --------------------------------------------------------

def test_aggregate_mean_over_evaluated_records_only():
    records = {
        "msg_0001": _record("msg_0001", "а б в"),          # wer 1/3
        "msg_0002": _record("msg_0002", "а б в"),          # wer 0.0
        "msg_0003": _record("msg_0003", None),             # excluded
    }
    results = _results(
        {"faster_whisper": {"msg_0001": "а б г", "msg_0002": "а б в", "msg_0003": "щось"}}
    )
    summary = W.evaluate(results, records)["summary"][0]
    assert summary["records_total"] == 3
    assert summary["records_with_reference"] == 2
    assert summary["records_with_hypothesis"] == 3
    assert summary["evaluated_records"] == 2
    assert summary["excluded_records"] == 1
    assert summary["wer"] == pytest.approx((1 / 3 + 0.0) / 2, abs=1e-6)
    assert summary["wer_status"] == W.MEASURED
    assert summary["cer_status"] == W.MEASURED


def test_aggregate_is_not_measured_with_zero_evaluated_records():
    records = {"msg_0001": _record("msg_0001", None)}
    results = _results({"faster_whisper": {"msg_0001": "текст"}})
    summary = W.evaluate(results, records)["summary"][0]
    assert summary["wer"] == M.NOT_MEASURED
    assert summary["cer"] == M.NOT_MEASURED
    assert summary["wer_status"] == W.NOT_MEASURABLE
    assert summary["cer_status"] == W.NOT_MEASURABLE


# --- 9. deterministic serialization --------------------------------------------------

def test_serialization_schema_and_byte_determinism(tmp_path):
    records = {"msg_0001": _record("msg_0001", None)}
    results = _results({"faster_whisper": {"msg_0001": "текст"}, "vosk": {"msg_0001": ""}})

    first = W.write_wer_evidence(str(tmp_path), results, records)
    snapshot = {name: open(path, "rb").read() for name, path in first.items()}
    second = W.write_wer_evidence(str(tmp_path), results, records)
    for name, path in second.items():
        assert open(path, "rb").read() == snapshot[name], name

    with open(first["wer_cer_results.csv"], encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert tuple(header) == W.WER_RESULT_FIELDS

    with open(first["wer_cer_summary.csv"], encoding="utf-8") as fh:
        assert tuple(next(csv.reader(fh))) == W.WER_SUMMARY_FIELDS

    with open(first["hypothesis_availability_matrix.csv"], encoding="utf-8") as fh:
        assert tuple(next(csv.reader(fh))) == W.HYPOTHESIS_MATRIX_FIELDS

    # deterministic ordering: engine name ascending, then message_id
    engines = [r["engine"] for r in csv.DictReader(open(first["wer_cer_results.csv"], encoding="utf-8"))]
    assert engines == sorted(engines)


# --- hypothesis availability matrix --------------------------------------------------

def test_hypothesis_matrix_row_per_record_with_both_engines():
    records = {f"msg_{i:04d}": _record(f"msg_{i:04d}", None) for i in range(1, 68)}
    results = _results(
        {
            "faster_whisper": {f"msg_{i:04d}": ("text" if i <= 64 else "") for i in range(1, 68)},
            "vosk": {f"msg_{i:04d}": ("text" if i <= 53 else "") for i in range(1, 68)},
        }
    )
    matrix = W.build_hypothesis_matrix(results, records)
    assert len(matrix) == 67
    assert all(row["reference_transcript_available"] is False for row in matrix)
    assert sum(1 for r in matrix if r["faster_whisper_output_available"]) == 64
    assert sum(1 for r in matrix if r["vosk_output_available"]) == 53


def test_diagnostic_states_not_measurable_when_no_reference():
    records = {"msg_0001": _record("msg_0001", None)}
    results = _results({"faster_whisper": {"msg_0001": "текст"}})
    diagnostic = W.build_diagnostic(results, records)
    assert diagnostic["wer_status"] == W.NOT_MEASURABLE
    assert diagnostic["cer_status"] == W.NOT_MEASURABLE
    assert diagnostic["reference_transcripts_available"] == 0
    assert diagnostic["missing_evidence"]
    assert diagnostic["required_next_step"]


def test_diagnostic_reports_measured_when_reference_present():
    records = {"msg_0001": _record("msg_0001", "привіт світ")}
    results = _results({"faster_whisper": {"msg_0001": "привіт світ"}})
    diagnostic = W.build_diagnostic(results, records)
    assert diagnostic["wer_status"] == W.MEASURED
    assert diagnostic["cer_status"] == W.MEASURED


# --- 10. the WO-068 human-review source is untouched --------------------------------

@pytest.mark.skipif(
    not os.path.exists(HUMAN_REVIEW_CSV),
    reason="staged WO-068 human-review artifact not present in this environment",
)
def test_human_review_source_is_byte_identical_read_only():
    from wo069_dataset import sha256_file

    assert sha256_file(HUMAN_REVIEW_CSV) == RECORDED_HUMAN_REVIEW_SHA256


def test_human_review_source_has_no_transcript_or_callsign_column():
    """Proves the reference gap is structural, not a parsing failure."""
    if not os.path.exists(HUMAN_REVIEW_CSV):
        pytest.skip("staged WO-068 human-review artifact not present")
    with open(HUMAN_REVIEW_CSV, encoding="utf-8") as fh:
        header = fh.readline().strip().split(";")
    assert "transcript" not in header
    assert "reference_transcript" not in header
    assert "callsign" not in header
