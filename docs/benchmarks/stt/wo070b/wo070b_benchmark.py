"""WO-070B human-reference STT accuracy benchmark (WER/CER).

Consumes:
  * ``human_reference_transcripts.csv``  (human-entered reference transcripts)
  * WO-069 hypothesis snapshots (JSONL, ``type == "file"`` records carry the
    per-message ``message_id`` and hypothesis ``text``)

Produces:
  * ``per_message_results.csv``
  * ``aggregate_results.csv``
  * ``wo070b_results.json``

Guarantees:
  * join is strictly by ``message_id`` (never by row position);
  * only ``reference_status == HUMAN_VERIFIED`` with a non-empty reference is
    scored; NON_AUDIBLE and NO_HUMAN_TRANSCRIPT are excluded;
  * empty hypotheses ARE scored when the reference is valid (a deletion-only
    record), never silently dropped;
  * no engine is ranked, labelled "best", or selected;
  * the same normalization (``wo070b_normalize``) is applied to both sides.

This module is benchmark-only. It imports nothing from production code and
changes nothing in it.
"""

import csv
import json
import os

from . import wo070b_metrics as metrics
from . import wo070b_normalize as norm

HERE = os.path.dirname(os.path.abspath(__file__))

REFERENCE_COLUMNS = [
    "message_id",
    "stream_id",
    "reference_transcript",
    "reference_status",
    "reviewer",
    "review_time",
]

STATUS_HUMAN_VERIFIED = "HUMAN_VERIFIED"
STATUS_NON_AUDIBLE = "NON_AUDIBLE"
STATUS_NO_HUMAN_TRANSCRIPT = "NO_HUMAN_TRANSCRIPT"

ENGINES = ("faster_whisper", "vosk")

PER_MESSAGE_COLUMNS = [
    "message_id",
    "engine",
    "reference_transcript",
    "hypothesis",
    "wer",
    "cer",
]

AGGREGATE_COLUMNS = [
    "engine",
    "hypotheses",
    "reference_count",
    "evaluated_count",
    "empty_hypothesis_count",
    "substitutions",
    "deletions",
    "insertions",
    "WER",
    "CER",
]


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def load_reference(path):
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        for col in REFERENCE_COLUMNS:
            row.setdefault(col, "")
    return rows


def load_hypotheses(path):
    """Return {message_id: hypothesis_text} from a WO-069 raw JSONL snapshot."""
    hyps = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("type") != "file":
                continue
            mid = obj.get("message_id")
            if not mid:
                continue
            if mid in hyps:
                raise ValueError(f"duplicate hypothesis message_id: {mid}")
            hyps[mid] = obj.get("text") or ""
    return hyps


# --------------------------------------------------------------------------- #
# Integrity checks
# --------------------------------------------------------------------------- #
def count_transcript_stats(reference_rows):
    total = len(reference_rows)
    verified = sum(
        1 for r in reference_rows
        if r["reference_status"] == STATUS_HUMAN_VERIFIED and r["reference_transcript"].strip()
    )
    non_audible = sum(1 for r in reference_rows if r["reference_status"] == STATUS_NON_AUDIBLE)
    no_transcript = sum(
        1 for r in reference_rows if r["reference_status"] == STATUS_NO_HUMAN_TRANSCRIPT
    )
    empty_transcripts = sum(
        1 for r in reference_rows
        if r["reference_status"] == STATUS_HUMAN_VERIFIED and not r["reference_transcript"].strip()
    )
    seen = set()
    duplicates = []
    for r in reference_rows:
        mid = r["message_id"]
        if mid in seen:
            duplicates.append(mid)
        seen.add(mid)
    return {
        "TOTAL_RECORDS": total,
        "HUMAN_VERIFIED_TRANSCRIPTS": verified,
        "NON_AUDIBLE": non_audible,
        "NO_HUMAN_TRANSCRIPT": no_transcript,
        "EMPTY_TRANSCRIPTS": empty_transcripts,
        "DUPLICATE_MESSAGE_IDS": duplicates,
        "MISSING_MESSAGE_IDS": [],
    }


def map_message_ids(reference_rows, hypotheses):
    ref_ids = [r["message_id"] for r in reference_rows]
    hyp_ids = set(hypotheses.keys())
    ref_set = set(ref_ids)
    duplicates = sorted({mid for mid in ref_ids if ref_ids.count(mid) > 1})
    missing_ids = sorted(ref_set - hyp_ids)
    orphan_hypotheses = sorted(hyp_ids - ref_set)
    matched = sorted(ref_set & hyp_ids)
    return {
        "reference_ids": len(ref_ids),
        "hypothesis_ids": len(hyp_ids),
        "matched": len(matched),
        "duplicates": duplicates,
        "missing_ids": missing_ids,
        "orphan_hypotheses": orphan_hypotheses,
    }


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def evaluate_engine(engine, reference_rows, hypotheses):
    per_message = []
    aggregate = {
        "engine": engine,
        "hypotheses": len(hypotheses),
        "reference_count": 0,
        "evaluated_count": 0,
        "empty_hypothesis_count": 0,
        "substitutions": 0,
        "deletions": 0,
        "insertions": 0,
        "WER": None,
        "CER": None,
    }
    ref_word_total = 0
    ref_char_total = 0
    wer_num = 0
    cer_num = 0

    for row in reference_rows:
        if row["reference_status"] != STATUS_HUMAN_VERIFIED:
            continue
        if not row["reference_transcript"].strip():
            continue
        aggregate["reference_count"] += 1

        mid = row["message_id"]
        hypothesis = hypotheses.get(mid)
        if hypothesis is None:
            # orphan reference: no hypothesis -> excluded from scoring
            continue

        scored = metrics.score_pair(row["reference_transcript"], hypothesis, norm)
        if scored["wer"] is None or scored["cer"] is None:
            # empty reference denominator -> not scorable
            continue

        aggregate["evaluated_count"] += 1
        if not scored["hypothesis_normalized"]:
            aggregate["empty_hypothesis_count"] += 1
        aggregate["substitutions"] += scored["substitutions"]
        aggregate["deletions"] += scored["deletions"]
        aggregate["insertions"] += scored["insertions"]

        ref_tokens = norm.normalize_tokens(row["reference_transcript"])
        ref_chars = norm.normalize_characters(row["reference_transcript"])
        ref_word_total += len(ref_tokens)
        ref_char_total += len(ref_chars)
        wer_num += scored["substitutions"] + scored["deletions"] + scored["insertions"]
        cer_num += (
            scored["cer_substitutions"]
            + scored["cer_deletions"]
            + scored["cer_insertions"]
        )

        per_message.append(
            {
                "message_id": mid,
                "engine": engine,
                "reference_transcript": row["reference_transcript"],
                "hypothesis": hypothesis,
                "wer": scored["wer"],
                "cer": scored["cer"],
            }
        )

    if ref_word_total:
        aggregate["WER"] = wer_num / ref_word_total
    if ref_char_total:
        aggregate["CER"] = cer_num / ref_char_total

    return aggregate, per_message


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def _fmt(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(round(value, 6))
    return str(value)


def write_per_message(rows, path):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=PER_MESSAGE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _fmt(row.get(k)) for k in PER_MESSAGE_COLUMNS})


def write_aggregate(rows, path):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=AGGREGATE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _fmt(row.get(k)) for k in AGGREGATE_COLUMNS})


def run(reference_path, hypothesis_paths, out_dir):
    reference_rows = load_reference(reference_path)
    transcript_stats = count_transcript_stats(reference_rows)

    aggregates = []
    per_message = []
    mapping = {}
    for engine in ENGINES:
        hyp_path = hypothesis_paths[engine]
        hypotheses = load_hypotheses(hyp_path)
        mapping[engine] = map_message_ids(reference_rows, hypotheses)
        agg, pm = evaluate_engine(engine, reference_rows, hypotheses)
        aggregates.append(agg)
        per_message.extend(pm)

    os.makedirs(out_dir, exist_ok=True)
    write_per_message(per_message, os.path.join(out_dir, "per_message_results.csv"))
    write_aggregate(aggregates, os.path.join(out_dir, "aggregate_results.csv"))

    results = {
        "schema": "wo070b-results-v1",
        "normalization_id": norm.NORMALIZATION_ID,
        "metrics_id": metrics.METRICS_ID,
        "reference": {
            "path": os.path.basename(reference_path),
            "transcript_stats": transcript_stats,
        },
        "mapping": mapping,
        "aggregate": aggregates,
        "per_message_count": len(per_message),
    }
    with open(os.path.join(out_dir, "wo070b_results.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    return results
