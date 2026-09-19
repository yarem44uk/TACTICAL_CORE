"""WO-070B tests — human-reference WER/CER benchmark.

Covers (WO-070B §16): exact match, substitution, insertion, deletion, empty
hypothesis, empty reference handling, non-audible exclusion, missing reference
exclusion, message_id join, duplicate message_id detection, normalization, CER,
WER, deterministic output.

Units only: nothing here touches production code or the network.
"""

import csv
import json
import os

import pytest

from docs.benchmarks.stt.wo070b import wo070b_benchmark as B
from docs.benchmarks.stt.wo070b import wo070b_metrics as M
from docs.benchmarks.stt.wo070b import wo070b_normalize as N

HERE = os.path.dirname(os.path.abspath(__file__))
REFERENCE_CSV = os.path.join(HERE, "human_reference_transcripts.csv")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _score(ref, hyp):
    return M.score_pair(ref, hyp, N)


def _write_reference(path, rows):
    cols = ["message_id", "stream_id", "reference_transcript", "reference_status",
            "reviewer", "review_time"]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def _write_hypotheses(path, pairs):
    with open(path, "w", encoding="utf-8") as fh:
        for mid, text in pairs:
            fh.write(json.dumps({"type": "file", "message_id": mid, "text": text},
                                ensure_ascii=False) + "\n")
    return path


# --------------------------------------------------------------------------- #
# 1. exact match
# --------------------------------------------------------------------------- #
def test_exact_match_scores_zero():
    s = _score("Канал один", "Канал один")
    assert s["wer"] == 0.0
    assert s["cer"] == 0.0
    assert (s["substitutions"], s["deletions"], s["insertions"]) == (0, 0, 0)


# --------------------------------------------------------------------------- #
# 2. substitution
# --------------------------------------------------------------------------- #
def test_substitution_counts_one():
    s = _score("Канал один", "Канал два")
    assert s["substitutions"] == 1
    assert s["deletions"] == 0
    assert s["insertions"] == 0
    assert s["wer"] == 0.5  # 1 op / 2 reference words


# --------------------------------------------------------------------------- #
# 3. insertion
# --------------------------------------------------------------------------- #
def test_insertion_counts_one():
    s = _score("Канал один", "Канал один два")
    assert s["insertions"] == 1
    assert (s["substitutions"], s["deletions"]) == (0, 0)
    assert s["wer"] == 0.5


# --------------------------------------------------------------------------- #
# 4. deletion
# --------------------------------------------------------------------------- #
def test_deletion_counts_one():
    s = _score("Канал один два", "Канал один")
    assert s["deletions"] == 1
    assert (s["substitutions"], s["insertions"]) == (0, 0)
    assert s["wer"] == pytest.approx(1 / 3)


# --------------------------------------------------------------------------- #
# 5. empty hypothesis is scored, not excluded
# --------------------------------------------------------------------------- #
def test_empty_hypothesis_is_scored_as_deletions():
    s = _score("Канал один", "")
    assert s["wer"] == 1.0
    assert s["deletions"] == 2
    assert s["substitutions"] == 0
    assert s["insertions"] == 0
    assert s["cer"] == 1.0


# --------------------------------------------------------------------------- #
# 6. empty reference handling -> metric undefined, never 0 or 1
# --------------------------------------------------------------------------- #
def test_empty_reference_is_undefined():
    assert M.wer([], ["щось"]) is None
    assert M.cer("", "щось") is None
    s = _score("", "щось")
    assert s["wer"] is None and s["cer"] is None


def test_empty_reference_record_excluded_from_aggregate(tmp_path):
    ref = _write_reference(tmp_path / "ref.csv", [
        {"message_id": "msg_0001", "stream_id": "S1", "reference_transcript": "",
         "reference_status": "HUMAN_VERIFIED", "reviewer": "X", "review_time": "1"},
    ])
    hyp = _write_hypotheses(tmp_path / "h.jsonl", [("msg_0001", "щось")])
    rows = B.load_reference(str(ref))
    agg, pm = B.evaluate_engine("t", rows, B.load_hypotheses(str(hyp)))
    assert agg["evaluated_count"] == 0
    assert agg["WER"] is None and agg["CER"] is None
    assert pm == []


# --------------------------------------------------------------------------- #
# 7. non-audible exclusion
# --------------------------------------------------------------------------- #
def test_non_audible_excluded_from_scoring():
    rows = [{"message_id": "msg_0001", "stream_id": "S1", "reference_transcript": "",
             "reference_status": "NON_AUDIBLE", "reviewer": "", "review_time": ""}]
    hyps = {"msg_0001": "Thank you for watching!"}
    agg, pm = B.evaluate_engine("t", rows, hyps)
    assert agg["reference_count"] == 0
    assert agg["evaluated_count"] == 0
    assert pm == []


# --------------------------------------------------------------------------- #
# 8. missing reference exclusion (orphan hypothesis / orphan reference)
# --------------------------------------------------------------------------- #
def test_missing_hypothesis_for_valid_reference_is_excluded():
    rows = [{"message_id": "msg_0005", "stream_id": "S1",
             "reference_transcript": "Канал п'ять",
             "reference_status": "HUMAN_VERIFIED", "reviewer": "OLEH",
             "review_time": "17:43:00"}]
    agg, pm = B.evaluate_engine("t", rows, {})  # no hypothesis at all
    assert agg["reference_count"] == 1
    assert agg["evaluated_count"] == 0
    assert pm == []


def test_mapping_reports_orphans_and_missing():
    rows = [
        {"message_id": "msg_0002", "stream_id": "S1", "reference_transcript": "a",
         "reference_status": "HUMAN_VERIFIED", "reviewer": "", "review_time": ""},
        {"message_id": "msg_0003", "stream_id": "S1", "reference_transcript": "b",
         "reference_status": "HUMAN_VERIFIED", "reviewer": "", "review_time": ""},
    ]
    hyps = {"msg_0002": "a", "msg_0099": "z"}
    m = B.map_message_ids(rows, hyps)
    assert m["matched"] == 1
    assert m["missing_ids"] == ["msg_0003"]
    assert m["orphan_hypotheses"] == ["msg_0099"]


# --------------------------------------------------------------------------- #
# 9. message_id join (never by row position)
# --------------------------------------------------------------------------- #
def test_join_is_by_message_id_not_position():
    rows = [
        {"message_id": "msg_0002", "stream_id": "S1", "reference_transcript": "alpha",
         "reference_status": "HUMAN_VERIFIED", "reviewer": "", "review_time": ""},
        {"message_id": "msg_0003", "stream_id": "S1", "reference_transcript": "beta",
         "reference_status": "HUMAN_VERIFIED", "reviewer": "", "review_time": ""},
    ]
    # hypotheses supplied in the OPPOSITE order, keyed by id
    hyps = {"msg_0003": "beta", "msg_0002": "alpha"}
    agg, pm = B.evaluate_engine("t", rows, hyps)
    assert agg["evaluated_count"] == 2
    assert all(r["wer"] == 0.0 for r in pm)
    got = {r["message_id"]: r["hypothesis"] for r in pm}
    assert got == {"msg_0002": "alpha", "msg_0003": "beta"}


# --------------------------------------------------------------------------- #
# 10. duplicate message_id detection
# --------------------------------------------------------------------------- #
def test_duplicate_reference_message_id_detected():
    rows = [
        {"message_id": "msg_0002", "stream_id": "S1", "reference_transcript": "a",
         "reference_status": "HUMAN_VERIFIED", "reviewer": "", "review_time": ""},
        {"message_id": "msg_0002", "stream_id": "S1", "reference_transcript": "a",
         "reference_status": "HUMAN_VERIFIED", "reviewer": "", "review_time": ""},
    ]
    stats = B.count_transcript_stats(rows)
    assert stats["DUPLICATE_MESSAGE_IDS"] == ["msg_0002"]


def test_duplicate_hypothesis_message_id_rejected(tmp_path):
    hyp = _write_hypotheses(tmp_path / "h.jsonl",
                            [("msg_0002", "a"), ("msg_0002", "b")])
    with pytest.raises(ValueError):
        B.load_hypotheses(str(hyp))


# --------------------------------------------------------------------------- #
# 11. normalization
# --------------------------------------------------------------------------- #
def test_normalization_casefold_and_whitespace():
    assert N.normalize_text("  Канал   ОДИН  ") == "канал один"


def test_normalization_apostrophe_variants_unified():
    for variant in ["Канал п\u2019ять", "Канал п\u02bcять", "Канал п`ять", "Канал п'ять"]:
        assert N.normalize_text(variant) == "канал п'ять"


def test_normalization_strips_punctuation_and_ellipsis():
    assert N.normalize_text("Ваші ..") == "ваші"
    assert N.normalize_text("… чуєш Дід") == "чуєш дід"
    assert N.normalize_text("Дід, дай зворотній рахунок") == "дід дай зворотній рахунок"


def test_normalization_keeps_digits_and_none():
    assert N.normalize_text("Один 2 три") == "один 2 три"
    assert N.normalize_text(None) == ""
    assert N.normalize_text("") == ""


def test_normalization_is_applied_to_both_sides():
    assert _score("КАНАЛ", "канал")["wer"] == 0.0
    assert _score("Канал!", "канал,")["wer"] == 0.0
    assert _score("Канал ОДИН", "канал")["wer"] == 0.5  # 1 deletion / 2 reference words


# --------------------------------------------------------------------------- #
# 12. CER
# --------------------------------------------------------------------------- #
def test_cer_character_level():
    s = _score("канал", "канал")
    assert s["cer"] == 0.0
    s = _score("канал", "каналx")
    assert s["cer"] == pytest.approx(0.2)  # 1 insertion / 5 reference chars
    s = _score("аб", "ав")
    assert s["cer"] == pytest.approx(0.5)
    # CER unit strips whitespace: "ка нал" and "канал" are identical
    assert _score("ка нал", "канал")["cer"] == 0.0


def test_cer_defined_in_metrics():
    assert M.cer("абв", "абв")["cer"] == 0.0
    assert M.cer("", "x") is None


# --------------------------------------------------------------------------- #
# 13. WER
# --------------------------------------------------------------------------- #
def test_wer_definition():
    assert M.wer(["a", "b", "c", "d"], ["a", "b", "c", "d"])["wer"] == 0.0
    assert M.wer(["a", "b", "c", "d"], ["a", "x", "c", "d"])["wer"] == 0.25
    assert M.wer(["a", "b", "c", "d"], ["a", "b", "c"])["wer"] == 0.25
    assert M.wer(["a", "b", "c"], ["a", "b", "c", "d"])["wer"] == pytest.approx(1 / 3)
    assert M.wer([], ["a"]) is None


# --------------------------------------------------------------------------- #
# 14. deterministic output
# --------------------------------------------------------------------------- #
def test_deterministic_pipeline_output(tmp_path):
    ref_path = REFERENCE_CSV
    hyps = {
        "faster_whisper": os.path.join(HERE, "wo069_hypotheses_faster_whisper.jsonl"),
        "vosk": os.path.join(HERE, "wo069_hypotheses_vosk.jsonl"),
    }
    out1 = tmp_path / "a"
    out2 = tmp_path / "b"
    r1 = B.run(ref_path, hyps, str(out1))
    r2 = B.run(ref_path, hyps, str(out2))
    assert json.dumps(r1, sort_keys=True, ensure_ascii=False) == \
        json.dumps(r2, sort_keys=True, ensure_ascii=False)
    for name in ("per_message_results.csv", "aggregate_results.csv",
                 "wo070b_results.json"):
        b1 = (out1 / name).read_bytes()
        b2 = (out2 / name).read_bytes()
        assert b1 == b2, f"{name} not byte-identical across runs"


def test_reference_dataset_is_wellformed():
    rows = B.load_reference(REFERENCE_CSV)
    stats = B.count_transcript_stats(rows)
    assert stats["TOTAL_RECORDS"] == 67
    assert stats["DUPLICATE_MESSAGE_IDS"] == []
    assert stats["EMPTY_TRANSCRIPTS"] == 0
    assert [r["message_id"] for r in rows] == [f"msg_{i:04d}" for i in range(1, 68)]
    # every scored row carries text; every NON_AUDIBLE row carries none
    for r in rows:
        if r["reference_status"] == "NON_AUDIBLE":
            assert r["reference_transcript"] == ""
        if r["reference_status"] == "HUMAN_VERIFIED":
            assert r["reference_transcript"].strip() != ""
